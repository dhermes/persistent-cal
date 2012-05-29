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


"""Handler classes for all requests to persistent-cal."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import datetime
import json
import logging

# App engine specific libraries
from google.appengine.api import users
from google.appengine.ext import deferred
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import login_required

# App specific libraries
from google_api_utils import InitCredentials
from handler_utils import ExtendedHandler
from library import UpdateString
from library import UpdateUserSubscriptions
from library import WhiteList
from models import UserCal
from time_utils import ConvertToInterval


CREDENTIALS = None
# split week in 56 3 hour windows, and assign the entire list based on these
# windows (two day is really 42 hours, 14 units)
FREQUENCIES = {'three-hrs': [val for val in range(56)],
               'six-hrs': [2*val for val in range(56/2)],
               'half-day': [4*val for val in range(56/4)],
               'day': [8*val for val in range(56/8)],
               'two-day': [14*val for val in range(56/14)],
               'week': [56*val for val in range(56/56)]}


class MainHandler(ExtendedHandler):
  """Handles get requests to /; provides a UI for managing subscribed feeds."""

  @login_required
  def get(self):  # pylint:disable-msg=C0103
    """Main UI for persistent-cal.

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
      base_interval = ConvertToInterval(datetime.datetime.utcnow())
      user_cal = UserCal(key_name=current_user.user_id(),
                         owner=current_user,
                         calendars=[],
                         update_intervals=[base_interval])
      user_cal.put()

    # pylint:disable-msg=E1103
    self.RenderResponse('index.html',
                        id=current_user.email(),
                        calendars=json.dumps(user_cal.calendars),
                        frequency=UpdateString(user_cal.update_intervals))


class AddSubscription(ExtendedHandler):
  """Handles post requests to /add and will change add a user calendar feed."""

  def post(self):  # pylint:disable-msg=C0103
    """Handles post requests to /add.

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
      self.response.out.write(json.dumps('whitelist:fail'))
      logging.info('whitelist:fail')
      return

    current_user = users.get_current_user()
    if current_user is None:
      self.response.out.write(json.dumps('no_user:fail'))
      logging.info('no_user:fail')
      return

    user_cal = UserCal.get_by_key_name(current_user.user_id())
    if user_cal is None:
      user_cal = UserCal(key_name=current_user.user_id(),
                         owner=current_user,
                         calendars=[link])
    elif link not in user_cal.calendars and len(user_cal.calendars) < 4:
      user_cal.calendars.append(link)  # pylint:disable-msg=E1103
    else:
      if len(user_cal.calendars) >= 4:  # pylint:disable-msg=E1103
        msg = 'limit:fail'
      else:
        # link must be in user_cal.calendars already
        msg = 'contained:fail'
      self.response.out.write(json.dumps(msg))
      logging.info(msg)
      return

    user_cal.put()  # pylint:disable-msg=E1103

    global CREDENTIALS  # pylint:disable-msg=W0603
    if CREDENTIALS is None:
      logging.info('Credentials initialized')
      CREDENTIALS = InitCredentials()

    UpdateUserSubscriptions(user_cal, credentials=CREDENTIALS, defer_now=True)
    # pylint:disable-msg=E1103
    self.response.out.write(json.dumps(user_cal.calendars))


class ChangeFrequency(ExtendedHandler):
  """Handles put requests to /freq and will change frequency for a user."""

  def put(self):  # pylint:disable-msg=C0103
    """Handles put requests to /freq.

    Validates the user, the user calendar, and the frequency value from the
    post request. If any of those three are not valid, nothing in the datastore
    is updated and an appropriate error message is returned to the caller. (The
    AJAX call will handle each of these errors.)

    If they are correct, the UserCal entry in the datastore will have the
    update_intervals column updated and the caller will receive the verbose
    description of the update as well as the frequency value for the
    <select> element.
    """
    # Make sure change has been requested by a user before doing any work
    current_user = users.get_current_user()
    if current_user is None:
      self.response.out.write(json.dumps('no_user:fail'))
      logging.info('no_user:fail')
      return

    frequency = self.request.get('frequency', None)

    user_cal = UserCal.get_by_key_name(current_user.user_id())
    if frequency in FREQUENCIES and user_cal is not None:
      if user_cal.update_intervals:  # pylint:disable-msg=E1103
        base_interval = user_cal.update_intervals[0]  # pylint:disable-msg=E1103
      else:
        base_interval = ConvertToInterval(datetime.datetime.utcnow())

      update_intervals = [(base_interval + delta_val) % 56
                          for delta_val in FREQUENCIES[frequency]]

      user_cal.update_intervals = update_intervals
      user_cal.put()  # pylint:disable-msg=E1103
      self.response.out.write(UpdateString(update_intervals))
    else:
      if user_cal is None:
        msg = 'no_cal:fail'
      else:
        msg = 'wrong_freq:fail'
      self.response.out.write(json.dumps(msg))
      logging.info(msg)
      return


class GetInfoHandler(ExtendedHandler):
  """Handles get requests to /getinfo and returns calendar & frequency info."""

  def get(self):  # pylint:disable-msg=C0103
    """Handles get requests to /getinfo."""
    current_user = users.get_current_user()
    if current_user is None:
      self.response.out.write(json.dumps('no_user:fail'))
      logging.info('no_user:fail')
      return

    user_cal = UserCal.get_by_key_name(current_user.user_id())
    if user_cal is None:
      self.response.out.write(json.dumps('no_cal:fail'))
      logging.info('no_cal:fail')
      return

    # pylint:disable-msg=E1103
    freq_data = json.loads(UpdateString(user_cal.update_intervals))
    user_info = json.dumps((user_cal.calendars, freq_data[0]))
    self.response.out.write(user_info)


class DeferredHandler(deferred.TaskHandler, ExtendedHandler):
  """A webapp handler class that processes deferred invocations."""

  def post(self):  # pylint:disable-msg=C0103
    """Custom post handler for deferred queue.

    Uses the run_from_request method from deferred.TaskHandler to attempt to run
    a deferred job. Uses the post wrapper defined in ExtendedHandler to handle
    any errors that may occur in run_from_request.
    """
    self.run_from_request()


class OwnershipVerifyHandler(ExtendedHandler):
  """Handles / as well as redirects for login required."""

  def get(self):  # pylint:disable-msg=C0103
    """Serves a static HTML file with verification data."""
    self.RenderResponse('googlef7560eebc24762bb.html')


class AboutHandler(ExtendedHandler):
  """Serves the static about page."""

  def get(self):  # pylint:disable-msg=C0103
    """Serves a static HTML file with an about page."""
    self.RenderResponse('about.html')


class AboutRedirect(ExtendedHandler):
  """Redirects to the correct about page."""

  def get(self):  # pylint:disable-msg=C0103
    """Redirects to /about."""
    self.redirect('/about')


class Throw404(ExtendedHandler):
  """Catches all non-specified (404) requests."""

  def get(self):  # pylint:disable-msg=C0103
    """Serves a static HTML file with a 404 page."""
    self.error(404)
    self.RenderResponse('404.html')


APPLICATION = webapp.WSGIApplication([
    ('/', MainHandler),
    ('/workers', DeferredHandler),
    ('/add', AddSubscription),
    ('/freq', ChangeFrequency),
    ('/getinfo', GetInfoHandler),
    ('/googlef7560eebc24762bb.html', OwnershipVerifyHandler),
    ('/about', AboutHandler),
    ('/about.html', AboutRedirect),
    ('/.*', Throw404),
    ], debug=True)
