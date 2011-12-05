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


"""Handler classes for all requests to persistent-cal"""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
from datetime import datetime
import os
import simplejson

# App engine specific libraries
from google.appengine.api import users
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import WSGIApplication

# App specific libraries
from library import ConvertToInterval
from library import ExtendedHandler
from library import InitGCAL
from library import TaskHandler
from library import UpdateString
from library import UpdateUserSubscriptions
from library import WhiteList
from models import UserCal


GCAL = None
# split week in 56 3 hour windows, and assign the entire list based on these
# windows (two day is really 42 hours, 14 units)
FREQUENCIES = {'three-hrs': [val for val in range(56)],
               'six-hrs': [2*val for val in range(56/2)],
               'half-day': [4*val for val in range(56/4)],
               'day': [8*val for val in range(56/8)],
               'two-day': [14*val for val in range(56/14)],
               'week': [56*val for val in range(56/56)]}


class MainHandler(ExtendedHandler):
  """Handles get requests to /; provides a UI for managing subscribed feeds"""

  @login_required
  def get(self):
    """
    Main UI for persistent-cal

    If a user is not logged in, login_required will force them to log in before
    reaching this page. Once they arrive, if they do not have a user calendar
    in the datastore, one will be created for them and they will be set to
    update once a week in the current interval.

    The user's email, calendar subscriptions and frequency of updates are then
    surfaced through the UI via a template.
    """

    # guaranteed to be a user since login_required
    current_user = users.get_current_user()
    user_cal = UserCal.get_by_key_name(current_user.user_id())
    if user_cal is None:
      base_interval = ConvertToInterval(datetime.utcnow())
      user_cal = UserCal(key_name=current_user.user_id(),
                         owner=current_user,
                         calendars=[],
                         update_intervals=[base_interval])
      user_cal.put()

    template_vals = {'id': current_user.email(),
                     'calendars': simplejson.dumps(user_cal.calendars),
                     'frequency': UpdateString(user_cal.update_intervals)}

    path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
    self.response.out.write(template.render(path, template_vals))


class AddSubscription(ExtendedHandler):
  """Handles post requests to /add and will change add a user calendar feed"""

  def post(self):
    """
    Handles post requests to /add

    First validates the calendar-link from the post request against a whitelist
    of accepted calendar feed links and then validates the user. If either of
    these fail, nothing in the datastore is updated and an appropriate error
    message is returned to the caller. (The AJAX call will handle each of these
    errors.)

    Once validated, queries the datastore for the user calendar. If it does not
    exist, one is created in the datastore. If it exists and the item can be
    added, the user calendar is updated in the datastore. If it exists and the
    feed is already subscribed to or the user has already reached four feeds,
    no update will occur and an appropriate error message is returned to the
    caller. (The AJAX call will handle each of these errors.)

    In the valid case, the main Google calendar is updated with the events from
    the new feed, the user calendar entry is updated in the datastore and the
    caller will receive the calendar subscription list. (The AJAX call will
    handle this JSON and update the list for the user.)
    """
    link = self.request.get('calendar-link', '').strip()
    valid, _ = WhiteList(link)
    if not valid:
      self.response.out.write(simplejson.dumps('whitelist:fail'))
      return

    # TODO(dhermes): Make sure self.request.referrer is safe
    current_user = users.get_current_user()
    if current_user is None:
      self.response.out.write(simplejson.dumps('no_user:fail'))
      return

    user_cal = UserCal.get_by_key_name(current_user.user_id())
    if user_cal is None:
      user_cal = UserCal(key_name=current_user.user_id(),
                         owner=current_user,
                         calendars=[link])
    elif link not in user_cal.calendars and len(user_cal.calendars) < 4:
      user_cal.calendars.append(link)
    else:
      if len(user_cal.calendars) >= 4:
        self.response.out.write(simplejson.dumps('limit:fail'))
      elif link in user_cal.calendars:
        self.response.out.write(simplejson.dumps('contained:fail'))
      return

    user_cal.put()

    global GCAL
    if GCAL is None:
      GCAL = InitGCAL()

    # TODO(dhermes) since user_cal has already been updated/added, be sure
    #               this does not error out. If it does error out, catch the
    #               error and still leave this function. Also within UpSc,
    #               make sure all events that are added to GCal are also added
    #               to the datastore.
    UpdateUserSubscriptions([link], user_cal, GCAL, defer_now=True)
    self.response.out.write(simplejson.dumps(user_cal.calendars))


class ChangeFrequency(ExtendedHandler):
  """Handles post requests to /freq and will change frequency for a user"""

  def post(self):
    """
    Handles post requests to /freq

    Validates the user, the user calendar, and the frequency value from the
    post request. If any of those three are not valid, nothing in the datastore
    is updated and an appropriate error message is returned to the caller. (The
    AJAX call will handle each of these errors.)

    If they are correct, the UserCal entry in the datastore will have the
    update_intervals column updated and the caller will receive the verbose
    description of the update as well as the frequency value for the
    <select> element.
    """
    # TODO(dhermes): Make sure self.request.referrer is safe

    # Make sure change has been requested by a user before doing any work
    current_user = users.get_current_user()
    if current_user is None:
      self.response.out.write(simplejson.dumps('no_user:fail'))
      return

    frequency = self.request.get('frequency', None)
    user_cal = UserCal.get_by_key_name(current_user.user_id())
    if frequency in FREQUENCIES and user_cal is not None:
      if user_cal.update_intervals:
        base_interval = user_cal.update_intervals[0]
      else:
        base_interval = ConvertToInterval(datetime.utcnow())

      update_intervals = [(base_interval + val) % 56
                          for val in FREQUENCIES[frequency]]

      user_cal.update_intervals = update_intervals
      user_cal.put()
      self.response.out.write(UpdateString(update_intervals))
    else:
      if user_cal is None:
        self.response.out.write(simplejson.dumps('no_cal:fail'))
      else:
        self.response.out.write(simplejson.dumps('wrong_freq:fail'))
      return


class DeferredHandler(ExtendedHandler, TaskHandler):
  pass


class OwnershipVerifyHandler(ExtendedHandler):
  """Handles / as well as redirects for login required"""

  def get(self):
    """Serves a static HTML file with verification data"""
    path = os.path.join(os.path.dirname(__file__),
                        'googlef7560eebc24762bb.html')
    self.response.out.write(template.render(path, {}))


class AboutHandler(ExtendedHandler):
  """Serves the static about page"""

  def get(self):
    """Serves a static HTML file with an about page"""
    path = os.path.join(os.path.dirname(__file__), 'templates', 'about.html')
    self.response.out.write(template.render(path, {}))


class Throw404(ExtendedHandler):
  """Catches all non-specified (404) requests"""

  def get(self):
    """Serves a static HTML file with a 404 page"""
    self.error(404)
    path = os.path.join(os.path.dirname(__file__), 'templates', '404.html')
    self.response.out.write(template.render(path, {}))


application = WSGIApplication([
    ('/', MainHandler),
    ('/workers', DeferredHandler),
    ('/add', AddSubscription),
    ('/freq', ChangeFrequency),
    ('/googlef7560eebc24762bb.html', OwnershipVerifyHandler),
    ('/about.html', AboutHandler),
    ('/.*', Throw404),
    ], debug=True)


def main():
  run_wsgi_app(application)


if __name__ == '__main__':
  main()
