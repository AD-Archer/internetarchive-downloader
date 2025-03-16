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
        task = download_queue.get()
        if task is None:
            break
        
        task_id = task['id']
        with status_lock:
            download_status[task_id]['status'] = 'running'
        
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
                with status_lock:
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
                    cache_refresh=task.get('cache_refresh', False)
                )
            
            if hash_file_handler:
                hash_file_handler.close()
            
            with status_lock:
                download_status[task_id]['status'] = 'completed'
                download_status[task_id]['end_time'] = datetime.datetime.now().isoformat()
        
        except Exception as e:
            with status_lock:
                download_status[task_id]['status'] = 'failed'
                download_status[task_id]['errors'].append(str(e))
                download_status[task_id]['end_time'] = datetime.datetime.now().isoformat()
        
        finally:
            download_queue.task_done()

# Start worker thread
worker_thread = threading.Thread(target=download_worker, daemon=True)
worker_thread.start()

@app.route('/')
def index():
    """Render the home page"""
    return render_template('index.html')

@app.route('/download', methods=['GET', 'POST'])
def download():
    """Handle download form submission"""
    form = DownloadForm()
    
    if form.validate_on_submit():
        # Create a unique task ID
        task_id = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Parse identifiers and search terms
        identifiers = [id.strip() for id in form.identifiers.data.split('\n') if id.strip()]
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
    with status_lock:
        tasks = {k: v for k, v in download_status.items()}
    
    return render_template('status_list.html', tasks=tasks)

@app.route('/status/<task_id>')
def status(task_id):
    """Show status of a specific download task"""
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