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


"""Handler for cron update requests made from persistent-cal"""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
from datetime import datetime

# App engine specific libraries
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

# App specific libraries
from library import ConvertToInterval
from library import InitGCAL
from library import UpdateSubscription
from models import UserCal


class MainHandler(webapp.RequestHandler):

  def get(self):
    """Updates every three hours."""
    now = ConvertToInterval(datetime.utcnow())
    GCAL = None

    all_users = UserCal.all()
    for user in all_users:
      if now in user.update_intervals:
        for link in user.calendars:
          if GCAL is None:
            GCAL = InitGCAL()
          UpdateSubscription(link, user.owner, GCAL)


application = webapp.WSGIApplication([
  ('/cron', MainHandler),
  ], debug=True)


if __name__ == '__main__':
  run_wsgi_app(application)
