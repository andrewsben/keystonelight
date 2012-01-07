import copy
import json
import os
import sys

from nose import exc

from keystonelight import config
from keystonelight import logging
from keystonelight import models
from keystonelight import test
from keystonelight import utils


CONF = config.CONF


IDENTITY_API_REPO = 'git://github.com/openstack/identity-api.git'
KEYSTONE_REPO = 'git://github.com/openstack/keystone.git'
NOVACLIENT_REPO = 'git://github.com/rackspace/python-novaclient.git'


IDENTITY_SAMPLE_DIR = 'openstack-identity-api/src/docbkx/samples'
KEYSTONE_SAMPLE_DIR = 'keystone/content/common/samples'


class CompatTestCase(test.TestCase):
  """Test compatibility against various versions of keystone's docs.

  It should be noted that the docs for any given revision have rarely, if ever,
  reflected the actual usage or reliable sample output of the system, so these
  tests are largely a study of frustration and its effects on developer
  productivity.

  """

  def setUp(self):
    super(CompatTestCase, self).setUp()

    self.tenants_for_token = json.load(open(
        os.path.join(self.sampledir, 'tenants.json')))
    self.validate_token = json.load(open(
        os.path.join(self.sampledir, 'validatetoken.json')))
    # NOTE(termie): stupid hack to deal with the keystone samples being
    #               completely inconsistent
    self.validate_token['access']['user']['roles'][1]['id'] = u'235'
    self.admin_token = 'ADMIN'

    self.auth_response = json.load(open(
        os.path.join(self.sampledir, 'auth.json')))

    # validate_token call
    self.tenant_345 = self.identity_api.create_tenant(
        '345',
        models.Tenant(id='345', name='My Project'))
    self.user_123 = self.identity_api.create_user(
        '123',
        models.User(id='123',
                    name='jqsmith',
                    tenants=[self.tenant_345['id']],
                    password='password'))
    self.extras_123 = self.identity_api.create_extras(
        self.user_123['id'], self.tenant_345['id'],
        dict(roles=[{'id': '234',
                     'name': 'compute:admin'},
                    {'id': '235',
                     'name': 'object-store:admin',
                     'tenantId': '1'}],
             roles_links=[]))
    self.token_123 = self.token_api.create_token(
        'ab48a9efdfedb23ty3494',
        models.Token(id='ab48a9efdfedb23ty3494',
                     expires='2010-11-01T03:32:15-05:00',
                     user=self.user_123,
                     tenant=self.tenant_345,
                     extras=self.extras_123))

    # auth call
    # NOTE(termie): the service catalog in the sample doesn't really have
    #               anything to do with the auth being returned, so just load
    #               it fully from a fixture and add it to our db
    # NOTE(termie): actually all the data is insane anyway, so don't bother
    #catalog = json.load(open(
    #    os.path.join(os.path.dirname(__file__),
    #                 'keystone_compat_diablo_sample_catalog.json')))
    #self.catalog_api.create_catalog(self.user_123['id'],
    #                                     self.tenant_345['id'],
    #                                     catalog)

    # tenants_for_token call
    self.user_foo = self.identity_api.create_user(
        'foo',
        models.User(id='foo', name='FOO', tenants=['1234', '3456']))
    self.tenant_1234 = self.identity_api.create_tenant(
        '1234',
        models.Tenant(id='1234',
                      name='ACME Corp',
                      description='A description ...',
                      enabled=True))
    self.tenant_3456 = self.identity_api.create_tenant(
        '3456',
        models.Tenant(id='3456',
                      name='Iron Works',
                      description='A description ...',
                      enabled=True))

    self.token_foo_unscoped = self.token_api.create_token(
        'foo_unscoped',
        models.Token(id='foo_unscoped',
                     user=self.user_foo))
    self.token_foo_scoped = self.token_api.create_token(
        'foo_scoped',
        models.Token(id='foo_scoped',
                     user=self.user_foo,
                     tenant=self.tenant_1234))


class DiabloCompatTestCase(CompatTestCase):
  def setUp(self):
    CONF(config_files=['keystone_compat_diablo.conf'])

    revdir = test.checkout_vendor(KEYSTONE_REPO, 'stable/diablo')
    self.sampledir = os.path.join(revdir, KEYSTONE_SAMPLE_DIR)
    self.app = self.loadapp('keystone_compat_diablo')

    self.load_backends()
    super(DiabloCompatTestCase, self).setUp()

  def test_authenticate_scoped(self):
    # NOTE(termie): the docs arbitrarily changed and inserted a 'u' in front
    #               of one of the user ids, but none of the others
    raise exc.SkipTest('The docs have arbitrarily changed.')
    client = self.client(self.app)
    post_data = json.dumps(
        {'auth': {'passwordCredentials': {'username': self.user_123['id'],
                                          'password': self.user_123['password'],
                                          },
                  'tenantName': self.tenant_345['name']}})

    resp = client.post('/v2.0/tokens', body=post_data)
    data = json.loads(resp.body)
    logging.debug('KEYS: %s', data['access'].keys())
    self.assert_('expires' in data['access']['token'])
    self.assertDeepEquals(self.auth_response['access']['user'],
                          data['access']['user'])
    # there is pretty much no way to generate sane data that corresponds to
    # the sample data
    #self.assertDeepEquals(self.auth_response['access']['serviceCatalog'],
    #                      data['access']['serviceCatalog'])

  def test_validate_token_scoped(self):
    raise exc.SkipTest('The docs conflict with regular usage.')
    client = self.client(self.app, token=self.admin_token)
    resp = client.get('/v2.0/tokens/%s' % self.token_123['id'])
    data = json.loads(resp.body)
    self.assertDeepEquals(self.validate_token, data)

  def test_tenants_for_token_unscoped(self):
    # get_tenants_for_token
    client = self.client(self.app, token=self.token_foo_unscoped['id'])
    resp = client.get('/v2.0/tenants')
    data = json.loads(resp.body)
    self.assertDeepEquals(self.tenants_for_token, data)

  def test_tenants_for_token_scoped(self):
    # get_tenants_for_token
    client = self.client(self.app, token=self.token_foo_scoped['id'])
    resp = client.get('/v2.0/tenants')
    data = json.loads(resp.body)
    self.assertDeepEquals(self.tenants_for_token, data)
