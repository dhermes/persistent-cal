#!/usr/bin/python

# Copyright (C) 2010-2012 Google Inc.
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


__author__ = 'daniel.j.hermes@gmail.com (Daniel Hermes)'


# General libraries
import datetime

# App engine specific libraries
import webapp2

# App specific libraries
from google_api_utils import InitCredentials
from handler_utils import ExtendedHandler
from library import MonthlyCleanup
from library import UpdateUserSubscriptions
from models import UserCal
from time_utils import ConvertToInterval


class MainHandler(ExtendedHandler):
  """Handles cron requests to /cron.

  This handler carries out updates for any user scheduled to get an update
  during that update interval.
  """

  def get(self):  # pylint:disable-msg=C0103
    """Updates every three hours."""
    # ('http://code.google.com/appengine/docs/python/tools/webapp/'
    #  'requestclass.html#Request_headers')
    # http://docs.webob.org/en/latest/reference.html#headers
    # "Keys are case-insensitive."
    if self.request.headers.get('X-AppEngine-Cron', '') != 'true':
      # Check header for X-AppEngine-Cron: true
      # Don't run if not
      return

    now = datetime.datetime.utcnow()
    now_interval = ConvertToInterval(now)
    credentials = None

    current_users = UserCal.query(UserCal.update_intervals == now_interval)
    for user_cal in current_users:
      if user_cal.calendars:
        if credentials is None:
          credentials = InitCredentials()
        # pylint:disable-msg=E1123
        UpdateUserSubscriptions(user_cal, credentials=credentials,
                                defer_now=True)


class CleanupHandler(ExtendedHandler):
  """Handles cron requests to /cron-monthly.

  Cleans up any events older than three months by using MonthlyCleanup.
  """

  def get(self):  # pylint:disable-msg=C0103
    """Updates once a month."""
    if self.request.headers.get('X-AppEngine-Cron', '') != 'true':
      return

    now = datetime.datetime.utcnow()
    MonthlyCleanup(now.date(), defer_now=True)  # pylint:disable-msg=E1123


APPLICATION = webapp2.WSGIApplication([
    ('/cron', MainHandler),
    ('/cron-monthly', CleanupHandler),
    ], debug=True)
