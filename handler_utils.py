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


"""Handler utility library for persistent-cal."""


__author__ = 'dhermes@google.com (Daniel Hermes)'


# General libraries
import functools
import logging
import sys
import traceback

# App engine specific libraries
from google.appengine.api import mail
from google.appengine.api import urlfetch_errors
from google.appengine.ext.deferred import defer
from google.appengine.ext.deferred import PermanentTaskFailure
from google.appengine import runtime
import webapp2
from webapp2_extras import jinja2

# App specific libraries
from admins import ADMINS_TO


# Without using the kwarg 'app' in get_jinja2, webapp2.get_app() is
# used, which returns the active app instance.
# [Reference: http://webapp-improved.appspot.com/api/webapp2.html]
JINJA2_RENDERER = jinja2.get_jinja2()
RENDERED_500_PAGE = JINJA2_RENDERER.render_template('500.html')


def DeferFunctionDecorator(method):
  """Decorator that allows a function to accept a defer_now argument.

  Args:
    method: a callable object

  Returns:
    A new function which will do the same work as method, will also
        accept a defer_now keyword argument, and will log the arguments
        passed in. In the case that defer_now=True, the new function
        will spawn a task in the deferred queue at /workers.
  """
  @functools.wraps(method)
  def DeferrableMethod(*args, **kwargs):
    """Returned function that uses method from outside scope

    Adds behavior for logging and deferred queue.
    """
    logging.info('{method.func_name} called with: {locals!r}'.format(
        method=method, locals=locals()))

    defer_now = kwargs.pop('defer_now', False)
    if defer_now:
      kwargs['defer_now'] = False
      kwargs['_url'] = '/workers'

      defer(DeferrableMethod, *args, **kwargs)
    else:
      return method(*args, **kwargs)

  return DeferrableMethod


@DeferFunctionDecorator
def EmailAdmins(error_msg):
  """Sends email to admins with the preferred message, with option to defer.

  Uses the template error_notify.templ to generate an email with the {error_msg}
  sent to the list of admins in admins.ADMINS_TO.

  Args:
    error_msg: A string containing an error to be sent to admins by email
  """
  sender = 'Persistent Cal Errors <errors@persistent-cal.appspotmail.com>'
  subject = 'Persistent Cal Error: Admin Notify'
  body = JINJA2_RENDERER.render_template('error_notify.templ', error=error_msg)
  mail.send_mail(sender=sender, to=ADMINS_TO,
                 subject=subject, body=body)


def DeadlineDecorator(method):
  """Decorator for HTTP verbs to handle GAE timeout.

  Args:
    method: a callable object, expected to be a method of an object from
        a class that inherits from webapp.RequestHandler

  Returns:
    A new function which calls {method}, catches certain errors
        and responds to them gracefully
  """

  def WrappedMethod(self, *args, **kwargs):  # pylint:disable-msg=W0142
    """Returned function that uses method from outside scope.

    Tries to execute the method with the arguments. If either a
    PermanentTaskFailure is thrown (from deferred library) or if one of the two
    DeadlineExceededError's is thrown (inherits directly from BaseException)
    administrators are emailed and then cleanup occurs.
    """
    try:
      method(self, *args, **kwargs)
    except PermanentTaskFailure:
      # In this case, the function can't be run, so we alert but do not
      # raise the error, returning a 200 status code, hence killing the task.
      msg = 'Permanent failure attempting to execute task.'
      logging.exception(msg)
      EmailAdmins(msg, defer_now=True)  # pylint:disable-msg=E1123
    except (runtime.DeadlineExceededError,
            urlfetch_errors.DeadlineExceededError):
      # pylint:disable-msg=W0142
      traceback_info = ''.join(traceback.format_exception(*sys.exc_info()))
      logging.exception(traceback_info)
      EmailAdmins(traceback_info, defer_now=True)  # pylint:disable-msg=E1123

      self.response.clear()
      self.response.set_status(500)
      self.response.out.write(RENDERED_500_PAGE)

  return WrappedMethod


class ExtendedHandler(webapp2.RequestHandler):
  """A custom version of GAE webapp2.RequestHandler.

  This subclass of webapp2.RequestHandler defines a handle_exception
  function that will email administrators when an exception
  occurs. In addition, the __new__ method is overridden
  to allow custom wrappers to be placed around the HTTP verbs
  before an instance is created.
  """

  def __new__(cls, *args, **kwargs):  # pylint:disable-msg=W0142
    """Constructs the object.

    This is explicitly intended for Google App Engine's webapp2.RequestHandler.
    Requests only suport 7 of the 9 HTTP verbs, 4 of which we will
    decorate: get, post, put and delete. The other three supported
    (head, options, trace) may be added at a later time.
    Args:
      cls: A reference to the class

    Reference: ('http://code.google.com/appengine/docs/python/tools/'
                'webapp/requesthandlerclass.html')
    """
    verbs = ('get', 'post', 'put', 'delete')

    for verb in verbs:
      method = getattr(cls, verb, None)
      if callable(method):
        setattr(cls, verb, DeadlineDecorator(method))

    return super(ExtendedHandler, cls).__new__(cls, *args, **kwargs)

  @webapp2.cached_property
  def Jinja2(self):
    """Cached property holding a Jinja2 instance."""
    return jinja2.get_jinja2(app=self.app)

  def RenderResponse(self, template, **context):  # pylint:disable-msg=W0142
    """Use Jinja2 instance to render template and write to output.

    Args:
      template: filename (relative to ~/templates) that we are rendering
      context: keyword arguments corresponding to variables in template
    """
    rendered_value = self.Jinja2.render_template(template, **context)
    self.response.write(rendered_value)

  # pylint:disable-msg=C0103,W0613
  def handle_exception(self, exception, debug_mode):
    """Custom handler for all GAE errors that inherit from Exception.

    Args:
      exception: the exception that was thrown
      debug_mode: True if the web application is running in debug mode
    """
    traceback_info = ''.join(traceback.format_exception(*sys.exc_info()))
    logging.exception(traceback_info)
    EmailAdmins(traceback_info, defer_now=True)  # pylint:disable-msg=E1123

    self.response.clear()
    self.response.set_status(500)
    self.response.out.write(RENDERED_500_PAGE)
