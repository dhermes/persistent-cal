### Description

This repository contains server and client code for
the `persistent-cal` [App Engine][6] application.

The application enables persistent import of an [iCalendar][7] feed into a
Google Calendar.

**For example**, events from a [TripIt][5] feed can be
periodically added to a user's default Google Calendar (perhaps
one shared with coworkers or collaborators).

See the [about page][2] of the deployed version of this application
for more information

### Some Application Maintenance Tasks

- To update client libraries see Google API Python Client [Wiki][1].
- To debug cron jobs (I had to while dealing with the fix in [c9ca6f9][3]):

  ```python
  from google.appengine.api import urlfetch
  from scripts.persistent_cal import APIAuthManager

  auth_manager = APIAuthManager(raw_input('Email address: '))
  application_auth = auth_manager.GetApplicationAuth()
  cookie_header = 'ACSID=%s' % application_auth

  url = 'http://persistent-cal.appspot.com/cron-weekly'
  result = urlfetch.fetch(
      url=url, method=urlfetch.GET,
      headers={'Cookie': cookie_header, 'X-AppEngine-Cron': 'true'})

  url = 'http://persistent-cal.appspot.com/cron-monthly'
  result = urlfetch.fetch(
      url=url, method=urlfetch.GET,
      headers={'Cookie': cookie_header, 'X-AppEngine-Cron': 'true'})
  ```

- To PyLint the source code set these in the `bash` shell:

  ```bash
  $ APPENGINE_PATH="$(readlink `which appcfg.py` | xargs dirname)";
  $ WEBAPP2_PATH="$APPENGINE_PATH/lib/webapp2";
  $ PYTHONPATH=$PYTHONPATH:$APPENGINE_PATH:$WEBAPP2_PATH pylint \
  --rcfile=pylintrc library.py
  ```

- To add `google-api-python-client`, run `setup_dependencies.py`. This
  file will reflect the "latest" instructions from the client
  library [documentation][8].

- The version of `gae-pytz` in `setup_dependcies.py` reflects the
  "latest" from [PyPI][9].

**NOTE**: Repository was previously [hosted][4] on Google Code Hosting.

[1]: http://code.google.com/p/google-api-python-client/wiki/GoogleAppEngine
[2]: http://persistent-cal.appspot.com/about
[3]: https://github.com/dhermes/persistent-cal/commit/c9ca6f9c791c3c7f01975f1f87505ea5cf196d97
[4]: https://code.google.com/p/persistent-cal/
[5]: https://www.tripit.com/
[6]: https://cloud.google.com/products/app-engine/
[7]: http://en.wikipedia.org/wiki/ICalendar
[8]: https://developers.google.com/api-client-library/python/start/installation#appengine
[9]: https://pypi.python.org/pypi/gaepytz
