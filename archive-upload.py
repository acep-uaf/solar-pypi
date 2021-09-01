'''Python 3 script to compress, archive and upload data files to Google Drive.  Usage:
python3 archive-upload.py <path to configuration file>
Requires Python 3.6+ due to use of F-strings.  Also see requirements.txt for
list of non-standard-library packages required.
'''

import sys
import time
from pathlib import Path, PurePosixPath
import pickle
import bz2
from urllib.parse import urlparse
import logging, logging.handlers
import yaml
import boto3
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload

# --- Create Application working directory if it does not exist.
p_app = Path('~').expanduser() / '.archive-upload'
p_app.mkdir(exist_ok=True)

# --- Read in the configuration file that controls execution of the script.
# It is the first and required command line argument.
cfg_fn = sys.argv[1]
config = yaml.safe_load(open(cfg_fn, 'r'))

# ---------- Set Up Error and Info Logging

# set the log level. Because we are setting this on the logger, it will apply
# to all handlers (unless maybe you set a specific level on a handler?).
log_level = config.get('log-level', 'INFO')
logging.root.setLevel(getattr(logging, log_level))

# create a rotating file handler
# Create Log file directory if it does not exist.
# If log file directory is not in the configuration file, create
# a log directory in the application working directory.
p_log_dir = Path(config.get('log-file-dir', p_app / 'log'))
p_log_dir.mkdir(parents=True, exist_ok=True)
p_log = p_log_dir / 'archive-upload.log'

fh = logging.handlers.RotatingFileHandler(p_log, maxBytes=200000, backupCount=5)

# create formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(module)s - %(message)s')
fh.setFormatter(formatter)

# create a handler that will print to console as well.
console_h = logging.StreamHandler()
console_h.setFormatter(formatter)

# add the handlers to the root logger
logging.root.addHandler(fh)
logging.root.addHandler(console_h)

# ----- Logging setup done

# ---- Main processing starts here.

try:
    logging.info('Script start.')

    # Path to pickle file holding the list of files that need to be uploaded
    # but haven't been yet.  This is a list of two-tuples:
    # (local file path, S3 bucket/key to upload to)
    p_up_pending = p_app / 'upload_pending.pkl'

    # Read a list of pending uploads, if file is present, otherwise,
    # set to empty list.
    if p_up_pending.exists():
        with p_up_pending.open('rb') as fin:
            upload_pending = pickle.load(fin)
    else:
        upload_pending = []

    # Loop through the list of directories, looking for completed files.
    for dr in config['directories']:
        # Path to directory holding data files
        p_dr = Path(dr['directory'])

        # Path to directory where finished, compressed files will be archived
        p_archive = Path(dr['archive-dir'])

        # make the archive directory if it does not exists
        p_archive.mkdir(parents=True, exist_ok=True)

        # Loop through file patterns
        for pat in dr['file-patterns']:

            # number of seconds of age that make a file deemed complete.  If not
            # provided, default to 5 seconds which essentially assumes that any age
            # file is ready to be archived.
            age_test = pat['finished-secs'] if 'finished-secs' in pat else 5.0

            for p_f in p_dr.glob(pat['pattern']):

                # p_f is a Path to a file matching the pattern.
                # determine the time elapsed since last modification of the file.
                file_age = time.time() - p_f.stat().st_mtime
                # print(f'{p_f}, age: {file_age}, age test: {age_test}')

                if file_age > age_test:
                    # make Path to upcoming compressed, archived copy of file.
                    p_arch_fn = p_archive / (p_f.name + '.bz2')
                    try:
                        with bz2.open(p_arch_fn, "wb") as fout:
                            fout.write(p_f.read_bytes())

                        # add the archive file to the upload list. I'm converting the Path objects
                        # to strings so the pickle is more straight-forward.
                        new_upload = (str(p_arch_fn), str(PurePosixPath(dr['bucket-and-key']) / p_arch_fn.name))
                        upload_pending.append(new_upload)

                        # delete the source file
                        p_f.unlink()

                        logging.info(f'Archived {p_f}')

                    except Exception as e:
                        logging.exception(f'Error attempting to archive {p_f}')

        # Check for files to delete in the archive directory
        # but only delete if the file is not in the upload pending list
        if len(upload_pending):
            # extract out a list of file names; bucket destinations are not needed.
            pending_file_list = list(zip(*upload_pending))[0]
        else:
            pending_file_list = []
        if 'delete-after' in dr and dr['delete-after'] > 0:
            max_age = dr['delete-after'] * 24 * 3600.
            for p_f in p_archive.glob('*.bz2'):
                file_age = time.time() - p_f.stat().st_mtime
                if not str(p_f) in pending_file_list and file_age > max_age:
                    p_f.unlink()
                    logging.info(f'{p_f} deleted due to exceeding max age.')

    # Upload archived files
    s3 = boto3.resource('s3')

    # need to copy the list to iterate across it because this
    # codes deletes items out of the original list.
    for fn, bucket_key in upload_pending.copy():
        # if this file no longer exists, delete it from the upload list.
        if not Path(fn).exists():
            upload_pending.remove((fn, bucket_key))
            logging.info(f'{fn} does not exist, so will not be uploaded.')

 
        # Google Drive Upload Option
        try:
            credentials_file = dr.get("google-drive-key-file")
            scopes = dr.get("google-drive-scopes")
            target_drive_folders = [dr.get("google-drive-folder-id")]

            credentials = service_account.Credentials.from_service_account_file(credentials_file).with_scopes(scopes)
            drive_client = build('drive', 'v3', credentials=credentials)

            export_fname = fn.split("/")[-1]
            export_metadata = {'name':export_fname, 'parents':target_drive_folders}
            export_media = MediaFileUpload(fn, mimetype='application/octet-stream', resumable=True)
            drive_client.files().create(body=export_metadata,
                           media_body=export_media,
                           supportsAllDrives="true",
                           fields="id").execute()
            
            upload_pending.remove((fn, bucket_key))
            logging.info(f'Uploaded {fn}')
        
        except Exception as e:
            logging.exception(f"Error attempting to upload {fn} to Google Drive")


except:
    logging.exception('General error.')

finally:
    if 'upload_pending' in locals():
        # save the list of archive files that still need to be uploaded.
        with p_up_pending.open('wb') as fout:
            pickle.dump(upload_pending, fout)
