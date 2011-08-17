# General libraries
from datetime import datetime
import os
import simplejson
from urllib2 import urlparse

# App engine specific libraries
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp.util import run_wsgi_app

# App specific libraries
from library import ConvertToInterval
from library import InitGCAL
from library import UpdateString
from library import UpdateSubscription
from models import UserCal


GCAL = None
FREQUENCIES = {'three-hrs': [val for val in range(56)],
               'six-hrs': [2*val for val in range(56/2)],
               'half-day': [4*val for val in range(56/4)],
               'day': [8*val for val in range(56/8)],
               'two-day': [14*val for val in range(56/14)],
               'week': [56*val for val in range(56/56)]}


class MainHandler(webapp.RequestHandler):

  @login_required
  def get(self):
    """This handler is responsible for fetching an initial OAuth
    request token and redirecting the user to the approval page."""

    # gauranteed to be a user since login_required
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
                     'can_add': (len(user_cal.calendars) < 4),
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

    if GCAL is None:
      global GCAL
      GCAL = InitGCAL()

    UpdateSubscription(link, current_user, GCAL)
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
      # In the case set_interval is True, update_intervals will be set
      user_cal.update_intervals = update_intervals
      user_cal.put()
      self.response.out.write(UpdateString(update_intervals))


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
