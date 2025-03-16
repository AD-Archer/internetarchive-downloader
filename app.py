#!/usr/bin/env python3

"""Flask web application for Internet Archive Downloader"""

import os
import threading
import queue
import datetime
import json
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField, IntegerField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, Optional, NumberRange
import ia_downloader

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing')
app.config['UPLOAD_FOLDER'] = 'downloads'
app.config['LOG_FOLDER'] = 'ia_downloader_logs'

# Create necessary folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['LOG_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['LOG_FOLDER'], 'logs'), exist_ok=True)
os.makedirs(os.path.join(app.config['LOG_FOLDER'], 'cache'), exist_ok=True)

# Queue for storing download tasks
download_queue = queue.Queue()
# Dictionary to store download status
download_status = {}
# Lock for thread-safe operations
status_lock = threading.Lock()
# Worker thread reference
worker_thread = None

class DownloadForm(FlaskForm):
    """Form for downloading Internet Archive items"""
    identifiers = TextAreaField('Internet Archive Identifiers (one per line)', validators=[Optional()])
    search_terms = TextAreaField('Search Terms (one per line)', validators=[Optional()])
    output_folder = StringField('Output Folder', validators=[DataRequired()], default='downloads')
    thread_count = IntegerField('Thread Count', validators=[NumberRange(min=1, max=5)], default=3)
    verify = BooleanField('Verify Downloads', default=True)
    resume = BooleanField('Resume Interrupted Downloads', default=True)
    split_count = IntegerField('Split Count', validators=[NumberRange(min=1, max=5)], default=1)
    file_filters = StringField('File Filters (space separated)', validators=[Optional()])
    invert_file_filtering = BooleanField('Invert File Filtering', default=False)
    credentials_email = StringField('IA Email (optional)', validators=[Optional()])
    credentials_password = StringField('IA Password (optional)', validators=[Optional()])
    cache_refresh = BooleanField('Refresh Cache', default=False)
    submit = SubmitField('Start Download')

class VerifyForm(FlaskForm):
    """Form for verifying downloaded Internet Archive items"""
    data_folders = StringField('Data Folders (space separated)', validators=[DataRequired()], default='downloads')
    identifiers = StringField('Internet Archive Identifiers (space separated)', validators=[Optional()])
    file_filters = StringField('File Filters (space separated)', validators=[Optional()])
    invert_file_filtering = BooleanField('Invert File Filtering', default=False)
    no_paths = BooleanField('Ignore Paths', default=False)
    submit = SubmitField('Verify Downloads')

def download_worker():
    """Worker thread to process download tasks from the queue"""
    while True:
        try:
            # Get task with a timeout to allow for graceful shutdown
            task = download_queue.get(timeout=60)
            if task is None:
                break
            
            task_id = task['id']
            with status_lock:
                download_status[task_id]['status'] = 'running'
                # Initialize progress tracking
                download_status[task_id]['progress'] = {
                    'total_files': 0,
                    'completed_files': 0,
                    'current_file': None,
                    'current_file_progress': 0,
                    'current_file_size': 0
                }
            
            try:
                # Set up hash file if needed
                hash_file_handler = None
                if task.get('hash_file'):
                    hash_file_handler = open(task['hash_file'], 'w', encoding='utf-8')
                
                # Process identifiers
                identifiers = task.get('identifiers', [])
                
                # Process search terms
                if task.get('search_terms'):
                    for search in task['search_terms']:
                        # Check if task has been stopped
                        with status_lock:
                            if download_status[task_id]['status'] == 'stopped':
                                break
                                
                        search_results = ia_downloader.get_identifiers_from_search_term(
                            search=search,
                            cache_parent_folder=os.path.join(app.config['LOG_FOLDER'], 'cache'),
                            cache_refresh=task.get('cache_refresh', False)
                        )
                        identifiers.extend(search_results)
                
                # Set credentials if provided
                if task.get('credentials'):
                    try:
                        ia_downloader.internetarchive.configure(
                            task['credentials'][0], 
                            task['credentials'][1]
                        )
                    except Exception as e:
                        with status_lock:
                            download_status[task_id]['errors'].append(f"Authentication error: {str(e)}")
                
                # Process each identifier
                for identifier in identifiers:
                    # Check if task has been stopped
                    with status_lock:
                        if download_status[task_id]['status'] == 'stopped':
                            break
                            
                        download_status[task_id]['current_item'] = identifier
                    
                    ia_downloader.download(
                        identifier=identifier,
                        output_folder=task['output_folder'],
                        hash_file=hash_file_handler,
                        thread_count=task.get('thread_count', 3),
                        resume_flag=task.get('resume', True),
                        verify_flag=task.get('verify', True),
                        split_count=task.get('split_count', 1),
                        file_filters=task.get('file_filters'),
                        invert_file_filtering=task.get('invert_file_filtering', False),
                        cache_parent_folder=os.path.join(app.config['LOG_FOLDER'], 'cache'),
                        cache_refresh=task.get('cache_refresh', False),
                        task_id=task_id,  # Pass task_id for progress tracking
                        status_lock=status_lock,  # Pass status_lock for thread-safe updates
                        download_status=download_status  # Pass download_status for updates
                    )
                
                if hash_file_handler:
                    hash_file_handler.close()
                
                with status_lock:
                    # Only mark as completed if it wasn't stopped
                    if download_status[task_id]['status'] != 'stopped':
                        download_status[task_id]['status'] = 'completed'
                    download_status[task_id]['end_time'] = datetime.datetime.now().isoformat()
            
            except Exception as e:
                with status_lock:
                    # Only mark as failed if it wasn't stopped
                    if download_status[task_id]['status'] != 'stopped':
                        download_status[task_id]['status'] = 'failed'
                    download_status[task_id]['errors'].append(str(e))
                    download_status[task_id]['end_time'] = datetime.datetime.now().isoformat()
            
            finally:
                download_queue.task_done()
        except queue.Empty:
            # Queue timeout - continue waiting
            continue
        except Exception as e:
            # Log any unexpected errors but keep the worker running
            print(f"Unexpected error in download worker: {str(e)}")
            continue

def ensure_worker_thread():
    """Ensure the worker thread is running, start it if needed"""
    global worker_thread
    
    if worker_thread is None or not worker_thread.is_alive():
        worker_thread = threading.Thread(target=download_worker, daemon=True)
        worker_thread.start()

# Start worker thread
ensure_worker_thread()

@app.route('/')
def index():
    """Render the home page"""
    return render_template('index.html')

@app.route('/download', methods=['GET', 'POST'])
def download():
    """Handle download form submission"""
    # Ensure worker thread is running
    ensure_worker_thread()
    
    form = DownloadForm()
    
    if form.validate_on_submit():
        # Create a unique task ID
        task_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Parse identifiers and search terms
        raw_identifiers = [id.strip() for id in form.identifiers.data.split('\n') if id.strip()]
        # Process URLs to extract proper identifiers
        identifiers = []
        for raw_id in raw_identifiers:
            # If it's a URL, extract the identifier
            if raw_id.startswith('http'):
                # Extract identifier from URL like https://archive.org/details/identifier
                parts = raw_id.split('/details/')
                if len(parts) > 1:
                    # Get the identifier part and remove any trailing parameters
                    identifier = parts[1].split('?')[0].split('#')[0]
                    identifiers.append(identifier)
                else:
                    # If we can't parse it, use as is
                    identifiers.append(raw_id)
            else:
                # Not a URL, use as is
                identifiers.append(raw_id)
                
        search_terms = [term.strip() for term in form.search_terms.data.split('\n') if term.strip()]
        
        if not identifiers and not search_terms:
            flash('Please provide at least one identifier or search term', 'error')
            return render_template('download.html', form=form)
        
        # Parse file filters
        file_filters = None
        if form.file_filters.data:
            file_filters = [f.strip() for f in form.file_filters.data.split() if f.strip()]
        
        # Create output folder
        output_folder = os.path.join(app.config['UPLOAD_FOLDER'], form.output_folder.data)
        os.makedirs(output_folder, exist_ok=True)
        
        # Create hash file path
        hash_file = os.path.join(app.config['LOG_FOLDER'], f"{task_id}_hashes.txt")
        
        # Create credentials tuple if provided
        credentials = None
        if form.credentials_email.data and form.credentials_password.data:
            credentials = (form.credentials_email.data, form.credentials_password.data)
        
        # Create task
        task = {
            'id': task_id,
            'identifiers': identifiers,
            'search_terms': search_terms,
            'output_folder': output_folder,
            'thread_count': form.thread_count.data,
            'verify': form.verify.data,
            'resume': form.resume.data,
            'split_count': form.split_count.data,
            'file_filters': file_filters,
            'invert_file_filtering': form.invert_file_filtering.data,
            'credentials': credentials,
            'hash_file': hash_file,
            'cache_refresh': form.cache_refresh.data
        }
        
        # Initialize status
        with status_lock:
            download_status[task_id] = {
                'status': 'queued',
                'start_time': datetime.datetime.now().isoformat(),
                'end_time': None,
                'identifiers': identifiers,
                'search_terms': search_terms,
                'current_item': None,
                'errors': []
            }
        
        # Add task to queue
        download_queue.put(task)
        
        flash(f'Download task {task_id} has been queued', 'success')
        return redirect(url_for('status', task_id=task_id))
    
    return render_template('download.html', form=form)

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    """Handle verify form submission"""
    form = VerifyForm()
    
    if form.validate_on_submit():
        # Parse data folders
        data_folders = [folder.strip() for folder in form.data_folders.data.split() if folder.strip()]
        
        # Parse identifiers
        identifiers = None
        if form.identifiers.data:
            identifiers = [id.strip() for id in form.identifiers.data.split() if id.strip()]
        
        # Parse file filters
        file_filters = None
        if form.file_filters.data:
            file_filters = [f.strip() for f in form.file_filters.data.split() if f.strip()]
        
        # Run verification
        result = ia_downloader.verify(
            hash_file=None,  # Using cached data
            data_folders=data_folders,
            no_paths_flag=form.no_paths.data,
            hash_flag=True,
            cache_parent_folder=os.path.join(app.config['LOG_FOLDER'], 'cache'),
            identifiers=identifiers,
            file_filters=file_filters,
            invert_file_filtering=form.invert_file_filtering.data
        )
        
        if result:
            flash('Verification completed successfully!', 'success')
        else:
            flash('Verification completed with errors. Check the logs for details.', 'error')
        
        return redirect(url_for('index'))
    
    return render_template('verify.html', form=form)

@app.route('/status')
def status_list():
    """Show list of all download tasks"""
    # Ensure worker thread is running
    ensure_worker_thread()
    
    with status_lock:
        tasks = {k: v for k, v in download_status.items()}
    
    return render_template('status_list.html', tasks=tasks)

@app.route('/status/<task_id>')
def status(task_id):
    """Show status of a specific download task"""
    # Ensure worker thread is running
    ensure_worker_thread()
    
    with status_lock:
        task = download_status.get(task_id)
    
    if not task:
        flash(f'Task {task_id} not found', 'error')
        return redirect(url_for('index'))
    
    return render_template('status.html', task_id=task_id, task=task)

@app.route('/api/status/<task_id>')
def api_status(task_id):
    """API endpoint for getting task status"""
    with status_lock:
        task = download_status.get(task_id)
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    return jsonify(task)

@app.route('/api/stop/<task_id>', methods=['POST'])
def api_stop_task(task_id):
    """API endpoint for stopping a task"""
    with status_lock:
        task = download_status.get(task_id)
        
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        # Only allow stopping tasks that are running or queued
        if task['status'] not in ['running', 'queued']:
            return jsonify({'error': 'Task is not running or queued'}), 400
        
        # Mark the task as stopped
        task['status'] = 'stopped'
        task['end_time'] = datetime.datetime.now().isoformat()
        
    # Return success
    return jsonify({'success': True, 'message': 'Task stopped successfully'})

@app.route('/downloads/<path:filename>')
def download_file(filename):
    """Serve downloaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/logs')
def logs():
    """Show log files"""
    log_files = []
    log_dir = os.path.join(app.config['LOG_FOLDER'], 'logs')
    
    for file in os.listdir(log_dir):
        if file.endswith('.log'):
            log_files.append(file)
    
    return render_template('logs.html', log_files=log_files)

@app.route('/logs/<filename>')
def view_log(filename):
    """View contents of a log file"""
    log_dir = os.path.join(app.config['LOG_FOLDER'], 'logs')
    log_path = os.path.join(log_dir, filename)
    
    if not os.path.isfile(log_path):
        flash(f'Log file {filename} not found', 'error')
        return redirect(url_for('logs'))
    
    with open(log_path, 'r') as f:
        content = f.read()
    
    return render_template('view_log.html', filename=filename, content=content)

if __name__ == '__main__':
    # In production, the app will be behind a proxy/container
    # so we bind to 0.0.0.0 to allow external access
    app.run(host='0.0.0.0', port=9124, debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true') 