See the [about page][2] of the deployed version of this application.

This will allow a persistent import of one Google Calendar into another,
according to an update interval set by the user.

- To update client libraries see Google API Python Client [Wiki][1].
- To debug cron jobs (I had to while dealing with the fix in [c9ca6f9][3]):

        from google.appengine.api import urlfetch
        from scripts.persistent_cal import APIAuthManager

        auth_manager = APIAuthManager(raw_input('Email address: '))
        application_auth = auth_manager.GetApplicationAuth()
        cookie_header = 'ACSID=%s' % application_auth

        url = 'http://persistent-cal.appspot.com/cron-weekly'
        result = urlfetch.fetch(url=url, method=urlfetch.GET, 
                                headers={'Cookie': cookie_header, 'X-AppEngine-Cron': 'true'})

        url = 'http://persistent-cal.appspot.com/cron-monthly'
        result = urlfetch.fetch(url=url, method=urlfetch.GET, 
                                headers={'Cookie': cookie_header, 'X-AppEngine-Cron': 'true'})

- To PyLint the source code set these in the `bash` shell:

        APPENGINE_PATH="$(readlink `which appcfg.py` | xargs dirname)";
        WEBAPP2_PATH="$APPENGINE_PATH/lib/webapp2";
        PYTHONPATH=$PYTHONPATH:$APPENGINE_PATH:$WEBAPP2_PATH pylint --rcfile=pylintrc library.py

**NOTE**: Repository was previously [hosted][4] on Google Code Hosting.

[1]: http://code.google.com/p/google-api-python-client/wiki/GoogleAppEngine
[2]: http://persistent-cal.appspot.com/about
[3]: https://github.com/dhermes/persistent-cal/commit/c9ca6f9c791c3c7f01975f1f87505ea5cf196d97
[4]: https://code.google.com/p/persistent-cal/
