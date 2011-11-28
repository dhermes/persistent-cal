# http://code.google.com/appengine/docs/python/mail/emailmessagefields.html
ADMIN_LIST = [('Daniel Hermes', 'dhermes@google.com')]
ADMIN_LIST_AS_STR = ['%s <%s>' % (name, email) for name, email in ADMIN_LIST]
ADMINS_TO = ', '.join(ADMIN_LIST_AS_STR)
