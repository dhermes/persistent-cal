"""Gets new credentials using the keys in secret_key.py.

From Sample in project source wiki:
http://code.google.com/p/google-api-python-client/wiki/OAuth2#Command-Line
"""

import httplib2

from apiclient.discovery import build
from oauth2client.file import Storage
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.tools import run

from secret_key import CLIENT_ID
from secret_key import CLIENT_SECRET
from secret_key import DEVELOPER_KEY



storage = Storage('calendar.dat')
credentials = storage.get()

if credentials is None or credentials.invalid == True:
  flow = OAuth2WebServerFlow(
      client_id=CLIENT_ID,
      client_secret=CLIENT_SECRET,
      scope='https://www.google.com/calendar/feeds/',
      user_agent='persistent-cal-auth')

  credentials = run(flow, storage)
