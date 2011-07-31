import os
import pickle
import simplejson
from urllib2 import urlopen
from urllib2 import urlparse

###############
### EXAMPLE ###
###############
import gdata.gauth
# import gdata.docs.client
###############
###############
# import gdata
import gdata.calendar.client
from icalendar import Calendar

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp.util import run_wsgi_app

from models import Event
from secret_key import CONSUMER_KEY
from secret_key import CONSUMER_SECRET


def date_datetime_compare(val1, val2):
  if type(val1) == type(val2):
    return cmp(val1, val2)

  from datetime import datetime, date
  if val1.year != val2.year:
    return cmp(val1.year, val2.year)

  if val1.month != val2.month:
    return cmp(val1.month, val2.month)

  if val1.day != val2.day:
    return cmp(val1.day, val2.day)

  # We know same day, year and month, so val1 is 00:00:00
  if type(val1) == date and type(val2) == datetime:
    return -1
  elif type(val1) == datetime and type(val2) == date:
    return 1
  else:
    raise Exception("Bad data")


def pickle_event(event):
  # all events have a UID, and almost all begin with 'item-';
  # those that don't are an away event for the entire trip
  uid = unicode(event.get('uid'))
  to_pickle = {'when:from': event.get('dtstart').dt,
               'when:to': event.get('dtend').dt,
               'summary': unicode(event.get('summary')),
               'location': unicode(event.get('location')),
               'description': '%s\n\n%s\n%s' % (
                   unicode(event.get('description')),
                   '====================', uid)}
  return uid, pickle.dumps(to_pickle)


class MainHandler(webapp.RequestHandler):
  """Handles / as well as redirects for login required"""
  def get(self):
    path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
    self.response.out.write(template.render(path, {}))


class VerifyHandler(webapp.RequestHandler):
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

###############
### EXAMPLE ###
###############

# Constants included for ease of understanding. It is a more common
# and reliable practice to create a helper for reading a Consumer Key
# and Secret from a config file. You may have different consumer keys
# and secrets for different environments, and you also may not want to
# check these values into your source code repository.
SETTINGS = {
    'APP_NAME': 'persistent-cal',
    'CONSUMER_KEY': CONSUMER_KEY,
    'CONSUMER_SECRET': CONSUMER_SECRET,
    # 'SCOPES': ['https://docs.google.com/feeds/']
    'SCOPES': ['https://www.google.com/calendar/feeds/'],
    }

# Create an instance of the DocsService to make API calls
gcal = gdata.calendar.client.CalendarClient(source = SETTINGS['APP_NAME'])
# gdocs = gdata.docs.client.DocsClient(source = SETTINGS['APP_NAME'])

class Fetcher(webapp.RequestHandler):

  @login_required
  def get(self):
    """This handler is responsible for fetching an initial OAuth
    request token and redirecting the user to the approval page."""

    current_user = users.get_current_user()

    # We need to first get a unique token for the user to
    # promote.

    # We provide the callback URL. This is where we want the
    # user to be sent after they have granted us
    # access. Sometimes, developers generate different URLs
    # based on the environment. You want to set this value to
    # "http://localhost:8080/verify" if you are running the
    # development server locally.

    # We also provide the data scope(s). In general, we want
    # to limit the scope as much as possible. For this
    # example, we just ask for access to all feeds.
    scopes = SETTINGS['SCOPES']
    oauth_callback = 'http://%s/verify' % self.request.host
    consumer_key = SETTINGS['CONSUMER_KEY']
    consumer_secret = SETTINGS['CONSUMER_SECRET']
#     request_token = gdocs.get_oauth_token(scopes, oauth_callback,
#                                           consumer_key, consumer_secret)
    request_token = gcal.get_oauth_token(scopes, oauth_callback,
                                         consumer_key, consumer_secret)

    # Persist this token in the datastore.
    request_token_key = 'request_token_%s' % current_user.user_id()
    gdata.gauth.ae_save(request_token, request_token_key)

    # Generate the authorization URL.
    approval_page_url = request_token.generate_authorization_url()

    message = '<a href="%s">Request token for the Google Calendar Scope</a>'
    self.response.out.write(message % approval_page_url)


class RequestTokenCallback(webapp.RequestHandler):

  @login_required
  def get(self):
    """When the user grants access, they are redirected back to this
    handler where their authorized request token is exchanged for a
    long-lived access token."""

    current_user = users.get_current_user()

    # Remember the token that we stashed? Let's get it back from
    # datastore now and adds information to allow it to become an
    # access token.
    request_token_key = 'request_token_%s' % current_user.user_id()
    request_token = gdata.gauth.ae_load(request_token_key)
    gdata.gauth.authorize_request_token(request_token, self.request.uri)

    # We can now upgrade our authorized token to a long-lived
    # access token by associating it with gdocs client, and
    # calling the get_access_token method.
    if gcal.auth_token is None:
      gcal.auth_token = gcal.get_access_token(request_token)

    # Note that we want to keep the access token around, as it
    # will be valid for all API calls in the future until a user
    # revokes our access. For example, it could be populated later
    # from reading from the datastore or some other persistence
    # mechanism.
    access_token_key = 'access_token_%s' % current_user.user_id()
    gdata.gauth.ae_save(request_token, access_token_key)

    message = '<a href="%s">Let\'s get started</a>'
    self.response.out.write(message % '/started')


class StartedHandler(webapp.RequestHandler):

  @login_required
  def get(self):
    """Beep."""
    current_user = users.get_current_user()

    # Finally fetch the document list and print document title in
    # the response
    feed = gcal.GetAllCalendarsFeed()
    calendars = []
    for i, a_calendar in enumerate(feed.entry):
      calendars.append((i, a_calendar.title.text))

    path = os.path.join(os.path.dirname(__file__), 'templates', 'select.html')
    self.response.out.write(template.render(path, {'calendars': calendars}))


class CalendarHandler(webapp.RequestHandler):

  @login_required
  def get(self):
    """Beep."""
    current_user = users.get_current_user()

    # Finally fetch the document list and print document title in
    # the response
    chosen = self.request.get('cal', None)
    if chosen is not None:
      try:
        chosen = int(chosen)
      except (TypeError, ValueError):
        path = os.path.join(os.path.dirname(__file__),
                            'templates',
                            'index.html')
        self.response.out.write(template.render(path, {}))
        return

      link = ('webcal://www.tripit.com/feed/ical/private/'
              '3F43994D-4591D1AA4C63B1472D8D5D0E9568E5A8/tripit.ics')
      link = 'http:%s ' % urlparse.urlparse(link).path

      feed = urlopen(link)
      cal_feed = feed.read()
      feed.close()

      ical = Calendar.from_string(cal_feed)
      name = unicode(ical.get('X-WR-CALNAME'))
      pickled_vals = [pickle_event(component)
                      for component in ical.walk()
                      if component.name == "VEVENT"]
      uid_endings = ['====================\n%s' % x[0] for x in pickled_vals]
      times = sorted([pickle.loads(x[1])['when:from'] for x in pickled_vals],
                     cmp=date_datetime_compare)
      start_date = '%s-%02d-%02d' % (times[0].year,
                                     times[0].month,
                                     times[0].day)
      end_date = '%s-%02d-%02d' % (times[-1].year,
                                   times[-1].month,
                                   times[-1].day)
  
      uri = gcal.GetAllCalendarsFeed().entry[chosen].find_alternate_link()
      query = gdata.calendar.client.CalendarEventQuery()
      query.max_results = 50
      query.start_min = start_date
      query.start_max = end_date
      feed = gcal.GetCalendarEventFeed(uri=uri, q=query)
      calendar = []
      for i, an_event in enumerate(feed.entry):
        description = an_event.content.text
        if description is None:
          continue

        for ending in uid_endings:
          if description.endswith(ending):
            val = {'when:from': an_event.when[0].start
                       if an_event.when else None,
                   'when:to': an_event.when[0].end
                       if an_event.when else None,
                   'summary': an_event.title.text,
                   'location': an_event.where[0].value
                       if an_event.where else None,
                   'description': description}
            calendar.append((i, str(val)))

      path = os.path.join(os.path.dirname(__file__),
                          'templates',
                          'calendar.html')
      self.response.out.write(template.render(path, {'calendar': calendar}))
    else:
      path = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
      self.response.out.write(template.render(path, {}))

    
application = webapp.WSGIApplication([
  ###############
  ### EXAMPLE ###
  ###############
  ('/step1', Fetcher),
  ('/verify', RequestTokenCallback),
  ('/started', StartedHandler),
  ('/calendar', CalendarHandler),
  ###############
  ###############
  ('/googlef7560eebc24762bb.html', VerifyHandler),
  ('/', MainHandler),
  ('/.*', Throw404),
  ], debug=True)


def main():
    run_wsgi_app(application)


if __name__ == '__main__':
    main()
