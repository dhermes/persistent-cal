This will allow a persistent import of one Google Calendar into another,
according to user set intervals

To update client libraries see Google API Python Client [Wiki][1].
[1]: http://code.google.com/p/google-api-python-client/wiki/GoogleAppEngine

To debug cron jobs (I had to while dealing with the fix in c9ca6f9c791c3c7f01975f1f87505ea5cf196d97):

```
from google.appengine.api import urlfetch
from scripts.persistent_cal import APIAuthManager

auth_manager = APIAuthManager(raw_input('Email address: '))
application_auth = auth_manager.GetApplicationAuth()
cookie_header = 'ACSID=%s' % application_auth

url = 'http://persistent-cal.appspot.com/cron-weekly'
result = urlfetch.fetch(url=url, method=urlfetch.GET, headers={'Cookie': cookie_header, 'X-AppEngine-Cron': 'true'})

url = 'http://persistent-cal.appspot.com/cron-monthly'
result = urlfetch.fetch(url=url, method=urlfetch.GET, headers={'Cookie': cookie_header, 'X-AppEngine-Cron': 'true'})
```

PyLint-ing via:
```
APPENGINE_PATH="$(readlink `which appcfg.py` | xargs dirname)";
WEBAPP2_PATH="$APPENGINE_PATH/lib/webapp2";
PYTHONPATH=$PYTHONPATH:$APPENGINE_PATH:$WEBAPP2_PATH pylint --rcfile=pylintrc library.py
```