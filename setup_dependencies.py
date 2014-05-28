import os
import subprocess


GOOGLE_API_CLIENT_ZIP = ('https://google-api-python-client.googlecode.com'
                         '/files/google-api-python-client-gae-1.2.zip')
GOOGLE_API_CLIENT_FILENAME = os.path.split(GOOGLE_API_CLIENT_ZIP)[-1]


print 'Downloading google-api-python-client library:'
subprocess.call(['wget', GOOGLE_API_CLIENT_ZIP])
print 'Unzipping google-api-python-client library:'
subprocess.call(['unzip', '-q', GOOGLE_API_CLIENT_FILENAME])
