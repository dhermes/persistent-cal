import os
import urllib2

###############
### EXAMPLE ###
###############
import gdata.gauth
# import gdata.docs.client
###############
###############
# import gdata
import gdata.calendar.client
import icalendar

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp.util import run_wsgi_app

from secret_key import CONSUMER_KEY
from secret_key import CONSUMER_SECRET

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
    # "http://localhost:8080/step2" if you are running the
    # development server locally.

    # We also provide the data scope(s). In general, we want
    # to limit the scope as much as possible. For this
    # example, we just ask for access to all feeds.
    scopes = SETTINGS['SCOPES']
    oauth_callback = 'http://%s/step2' % self.request.host
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

    message = '<a href="%s">Request token for the Google Documents Scope</a>'
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
    gcal.auth_token = gcal.get_access_token(request_token)
    # gdocs.auth_token = gdocs.get_access_token(request_token)

    # Note that we want to keep the access token around, as it
    # will be valid for all API calls in the future until a user
    # revokes our access. For example, it could be populated later
    # from reading from the datastore or some other persistence
    # mechanism.
    access_token_key = 'access_token_%s' % current_user.user_id()
    gdata.gauth.ae_save(request_token, access_token_key)

    # Finally fetch the document list and print document title in
    # the response
    feed = gcal.GetCalendarEventFeed()
    for i, an_event in enumerate(feed.entry):
      print '\t%s. %s' % (i, an_event.title.text,)

#     feed = gdocs.GetDocList()
#     for entry in feed.entry:
#       template = '<div>%s</div>'
#       self.response.out.write(template % entry.title.text)

###############
###############

    
application = webapp.WSGIApplication([
  ###############
  ### EXAMPLE ###
  ###############
  ('/step1', Fetcher),
  ('/step2', RequestTokenCallback),
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
