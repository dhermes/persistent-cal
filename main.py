# General libraries
from datetime import datetime
import os
import simplejson
from urllib2 import urlparse

# Third-party libraries
import atom
import gdata.gauth
import gdata.calendar.client##

# App engine specific libraries
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp.util import run_wsgi_app

# App specific libraries
from library import ConvertToInterval
from library import UpdateSubscription
from models import UserCal
from secret_key import CONSUMER_KEY
from secret_key import CONSUMER_SECRET
from secret_key import TOKEN
from secret_key import TOKEN_SECRET


# Create an instance of the DocsService to make API calls
AUTH_TOKEN = gdata.gauth.OAuthHmacToken(consumer_key=CONSUMER_KEY,
                                        consumer_secret=CONSUMER_SECRET,
                                        token=TOKEN,
                                        token_secret=TOKEN_SECRET,
                                        auth_state=3)
GCAL = gdata.calendar.client.CalendarClient(source='persistent-cal')
GCAL.auth_token = AUTH_TOKEN

URI = ('https://www.google.com/calendar/feeds/'
       'vhoam1gb7uqqoqevu91liidi80%40group.calendar.google.com/private/full')
# FEED = GCAL.GetCalendarEventFeed(uri=URI)

FREQUENCIES = {'three-hrs': [val for val in range(56)],
               'six-hrs': [2*val for val in range(56/2)],
               'half-day': [4*val for val in range(56/4)],
               'day': [8*val for val in range(56/8)],
               'two-day': [14*val for val in range(56/14)],
               'week': [56*val for val in range(56/56)]}
RESPONSES = {1: ['once a week', 'week'],
             4: ['every two days', 'tw-day'],
             7: ['once a day', 'day'],
             14: ['twice a day', 'half-day'],
             28: ['every six hours', 'six-hrs'],
             56: ['every three hours', 'three-hrs']}

def UpdateString(update_intervals):
  length = len(update_intervals)
  if length not in RESPONSES:
    raise Exception("Bad interval length")
  else:
    return simplejson.dumps(RESPONSES[length])


class MainHandler(webapp.RequestHandler):

  @login_required
  def get(self):
    """This handler is responsible for fetching an initial OAuth
    request token and redirecting the user to the approval page."""

    # gauranteed to be a user since login_required
    current_user = users.get_current_user()
    user_cal = UserCal.get_by_key_name(current_user.user_id())
    calendars = [] if user_cal is None else user_cal.calendars

    template_vals = {'id': current_user.email(),
                     'calendars': simplejson.dumps(calendars),
                     'can_add': (len(calendars) < 4),
                     # TODO(dhermes) make sure user_cal exists
                     'frequency': UpdateString(user_cal.update_intervals)}

    # TODO(dhermes) look up UserCal and populate subscriptions/frequency
    path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
    self.response.out.write(template.render(path, template_vals))


class AddSubscription(webapp.RequestHandler):

  def post(self):
    # TODO(dhermes), server timeout caused event added to Gcal, but not
    # added to the datastore

    # TODO(dhermes): Add whitelist on adding for accepted providers
    # TODO(dhermes): Improve to take account for scheme (webcal not real scheme)
    link = self.request.get('calendar-link', '').strip()
    link = 'http:%s' % urlparse.urlparse(link).path

    # TODO(dhermes): make sure user is logged in
    current_user = users.get_current_user()

    user_cal = UserCal.get_by_key_name(current_user.user_id())
    if user_cal is None:
      user_cal = UserCal(key_name=current_user.user_id(),
                         owner=current_user,
                         calendars=[link])
    elif link not in user_cal.calendars and len(user_cal.calendars) < 4:
      # TODO(dhermes) send failure
      user_cal.calendars.append(link)

    user_cal.put()

    # UpdateSubscription(link, current_user, GCAL)
    self.response.out.write(simplejson.dumps(user_cal.calendars))


class ChangeFrequency(webapp.RequestHandler):

  def post(self):
    # TODO(dhermes), server timeout caused event added to Gcal, but not
    # added to the datastore
    frequency = self.request.get('frequency', None)
    set_interval = False
    if frequency in FREQUENCIES:
      # split week in 56 3 hour windows, and assign the entire
      # list based on these windows (two day is really 42 hours, 14 units)
      set_interval = True
      base_interval = ConvertToInterval(datetime.utcnow())
      # TODO(dhermes) don't allow users to get free updates; enforce
      # based on existing
      update_intervals = [(base_interval + val) % 56
                          for val in FREQUENCIES[frequency]]

    # TODO(dhermes): make sure user is logged in
    current_user = users.get_current_user()

    user_cal = UserCal.get_by_key_name(current_user.user_id())
    if user_cal is not None and set_interval:
      user_cal.update_intervals = update_intervals
      user_cal.put()
      self.response.out.write(
          simplejson.dumps(RESPONSES[len(update_intervals)]))


class OwnershipVerifyHandler(webapp.RequestHandler):
  """Handles / as well as redirects for login required"""

  def get(self):
    path = os.path.join(os.path.dirname(__file__),
                        'googlef7560eebc24762bb.html')
    self.response.out.write(template.render(path, {}))


class Throw404(webapp.RequestHandler):
  """Catches all non-specified (404) requests"""

  def get(self):
    self.error(404)
    path = os.path.join(os.path.dirname(__file__), 'templates', '404.html')
    self.response.out.write(template.render(path, {}))


application = webapp.WSGIApplication([
  ('/', MainHandler),
  ('/add', AddSubscription),
  ('/freq', ChangeFrequency),
  ('/googlef7560eebc24762bb.html', OwnershipVerifyHandler),
  ('/.*', Throw404),
  ], debug=True)


# TODO(dhermes): read
# http://code.google.com/appengine/docs/python/runtime.html#App_Caching
if __name__ == '__main__':
  run_wsgi_app(application)
