#!/usr/bin/python

# Copyright (C) 2010-2011 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Handler for cron update requests made from persistent-cal."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
from datetime import datetime

# App engine specific libraries
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import WSGIApplication

# App specific libraries
from library import ConvertToInterval
from library import ExtendedHandler
from library import InitCredentials
from library import MonthlyCleanup
from library import UpdateUserSubscriptions
from models import UserCal


class MainHandler(ExtendedHandler):

  def get(self):
    """Updates every three hours."""
    # ('http://code.google.com/appengine/docs/python/tools/webapp/'
    #  'requestclass.html#Request_headers')
    # http://docs.webob.org/en/latest/reference.html#headers
    # "Keys are case-insensitive."
    if self.request.headers.get('X-AppEngine-Cron', '') != 'true':
      # Check header for X-AppEngine-Cron: true
      # Don't run if not
      return

    now = datetime.utcnow()
    now_interval = ConvertToInterval(now)
    CREDENTIALS = None

    # TODO(dhermes) allow for DeadlineExceededError here as well, in the case
    #               that all_users becomes to big to set off background tasks
    all_users = UserCal.all()
    for user_cal in all_users:
      if now_interval in user_cal.update_intervals:
        if CREDENTIALS is None:
          CREDENTIALS = InitCredentials()
        UpdateUserSubscriptions(user_cal.calendars, user_cal,
                                CREDENTIALS, defer_now=True)


class CleanupHandler(ExtendedHandler):

  def get(self):
    """Updates once a month."""
    if self.request.headers.get('X-AppEngine-Cron', '') != 'true':
      return

    now = datetime.utcnow()
    MonthlyCleanup(now.date(), defer_now=True)


application = WSGIApplication([
    ('/cron', MainHandler),
    ('/cron-monthly', CleanupHandler),
    ], debug=True)


def main():
  run_wsgi_app(application)


if __name__ == '__main__':
  main()
