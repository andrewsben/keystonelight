"""SQL backends for the various services."""

import json

import eventlet.db_pool
import sqlalchemy as sql
from sqlalchemy import types as sql_types
from sqlalchemy.ext import declarative
import sqlalchemy.orm
import sqlalchemy.pool
import sqlalchemy.engine.url

from keystonelight import config
from keystonelight import models


CONF = config.CONF


Base = declarative.declarative_base()


# Special Fields
class JsonBlob(sql_types.TypeDecorator):
  impl = sql.Text

  def process_bind_param(self, value, dialect):
    return json.dumps(value)

  def process_result_value(self, value, dialect):
    return json.loads(value)


class DictBase(object):
  def to_dict(self):
    return dict(self.iteritems())

  def __setitem__(self, key, value):
    setattr(self, key, value)

  def __getitem__(self, key):
    return getattr(self, key)

  def get(self, key, default=None):
    return getattr(self, key, default)

  def __iter__(self):
    self._i = iter(sqlalchemy.orm.object_mapper(self).columns)
    return self

  def next(self):
    n = self._i.next().name
    return n

  def update(self, values):
    """Make the model object behave like a dict."""
    for k, v in values.iteritems():
      setattr(self, k, v)

  def iteritems(self):
    """Make the model object behave like a dict.

    Includes attributes from joins.

    """
    return dict([(k, getattr(self, k)) for k in self])
    #local = dict(self)
    #joined = dict([(k, v) for k, v in self.__dict__.iteritems()
    #               if not k[0] == '_'])
    #local.update(joined)
    #return local.iteritems()


# Tables
class User(Base, DictBase):
  __tablename__ = 'user'
  id = sql.Column(sql.String(64), primary_key=True)
  name = sql.Column(sql.String(64), unique=True)
  #password = sql.Column(sql.String(64))
  extra = sql.Column(JsonBlob())

  @classmethod
  def from_dict(cls, user_dict):
    # shove any non-indexed properties into extra
    extra = {}
    for k, v in user_dict.copy().iteritems():
      # TODO(termie): infer this somehow
      if k not in ['id', 'name']:
        extra[k] = user_dict.pop(k)

    user_dict['extra'] = extra
    return cls(**user_dict)

  def to_dict(self):
    extra_copy = self.extra.copy()
    extra_copy['id'] = self.id
    extra_copy['name'] = self.name
    return extra_copy


class Tenant(Base, DictBase):
  __tablename__ = 'tenant'
  id = sql.Column(sql.String(64), primary_key=True)
  name = sql.Column(sql.String(64), unique=True)
  extra = sql.Column(JsonBlob())

  @classmethod
  def from_dict(cls, tenant_dict):
    # shove any non-indexed properties into extra
    extra = {}
    for k, v in tenant_dict.copy().iteritems():
      # TODO(termie): infer this somehow
      if k not in ['id', 'name']:
        extra[k] = tenant_dict.pop(k)

    tenant_dict['extra'] = extra
    return cls(**tenant_dict)

  def to_dict(self):
    extra_copy = self.extra.copy()
    extra_copy['id'] = self.id
    extra_copy['name'] = self.name
    return extra_copy


class Role(Base, DictBase):
  __tablename__ = 'role'
  id = sql.Column(sql.String(64), primary_key=True)
  name = sql.Column(sql.String(64))


class Extras(Base, DictBase):
  __tablename__ = 'extras'
  #__table_args__ = (
  #    sql.Index('idx_extras_usertenant', 'user', 'tenant'),
  #    )

  user_id = sql.Column(sql.String(64), primary_key=True)
  tenant_id = sql.Column(sql.String(64), primary_key=True)
  data = sql.Column(JsonBlob())


class Token(Base, DictBase):
  __tablename__ = 'token'
  id = sql.Column(sql.String(64), primary_key=True)
  user = sql.Column(sql.String(64))
  tenant = sql.Column(sql.String(64))
  data = sql.Column(JsonBlob())


class UserTenantMembership(Base, DictBase):
  """Tenant membership join table."""
  __tablename__ = 'user_tenant_membership'
  user_id = sql.Column(sql.String(64),
                       sql.ForeignKey('user.id'),
                       primary_key=True)
  tenant_id = sql.Column(sql.String(64),
                         sql.ForeignKey('tenant.id'),
                         primary_key=True)


# Backends
class SqlBase(object):
  _MAKER = None
  _ENGINE = None

  def get_session(self, autocommit=True, expire_on_commit=False):
    """Return a SQLAlchemy session."""
    if self._MAKER is None or self._ENGINE is None:
      self._ENGINE = self.get_engine()
      self._MAKER = self.get_maker(self._ENGINE, autocommit, expire_on_commit)

    session = self._MAKER()
    # TODO(termie): we may want to do something similar
    #session.query = nova.exception.wrap_db_error(session.query)
    #session.flush = nova.exception.wrap_db_error(session.flush)
    return session

  def get_engine(self):
    """Return a SQLAlchemy engine."""
    connection_dict = sqlalchemy.engine.url.make_url(CONF.sql.connection)

    engine_args = {
        "pool_recycle": CONF.sql.idle_timeout,
        "echo": True,
        }

    if "sqlite" in connection_dict.drivername:
      engine_args["poolclass"] = sqlalchemy.pool.NullPool

    return sql.create_engine(CONF.sql.connection, **engine_args)

  def get_maker(self, engine, autocommit=True, expire_on_commit=False):
    """Return a SQLAlchemy sessionmaker using the given engine."""
    return sqlalchemy.orm.sessionmaker(bind=engine,
                                       autocommit=autocommit,
                                       expire_on_commit=expire_on_commit)


class SqlIdentity(SqlBase):
  def authenticate(self, user_id=None, tenant_id=None, password=None):
    """Authenticate based on a user, tenant and password.

    Expects the user object to have a password field and the tenant to be
    in the list of tenants on the user.

    """
    user_ref = self.get_user(user_id)
    tenant_ref = None
    extras_ref = None
    if not user_ref or user_ref.get('password') != password:
      raise AssertionError('Invalid user / password')

    tenants = self.get_tenants_for_user(user_id)
    if tenant_id and tenant_id not in tenants:
      raise AssertionError('Invalid tenant')

    tenant_ref = self.get_tenant(tenant_id)
    print 'ETESTSET', tenant_ref
    if tenant_ref:
      extras_ref = self.get_extras(user_id, tenant_id)
    else:
      extras_ref = {}
    return (user_ref, tenant_ref, extras_ref)

  def get_tenant(self, tenant_id):
    session = self.get_session()
    tenant_ref = session.query(Tenant).filter_by(id=tenant_id).first()
    if not tenant_ref:
      return
    return tenant_ref.to_dict()

  def get_tenant_by_name(self, tenant_name):
    session = self.get_session()
    tenant_ref = session.query(Tenant).filter_by(name=tenant_name).first()
    if not tenant_ref:
      return
    return tenant_ref.to_dict()

  def get_user(self, user_id):
    session = self.get_session()
    user_ref = session.query(User).filter_by(id=user_id).first()
    if not user_ref:
      return
    return user_ref.to_dict()

  def get_user_by_name(self, user_name):
    session = self.get_session()
    user_ref = session.query(User).filter_by(name=user_name).first()
    if not user_ref:
      return
    return user_ref.to_dict()

  def get_extras(self, user_id, tenant_id):
    session = self.get_session()
    extras_ref = session.query(Extras)\
                        .filter_by(user_id=user_id)\
                        .filter_by(tenant_id=tenant_id)\
                        .first()
    return getattr(extras_ref, 'data', None)

  def get_role(self, role_id):
    session = self.get_session()
    role_ref = session.query(Role).filter_by(id=role_id).first()
    return role_ref

  def list_users(self):
    session = self.get_session()
    user_refs = session.query(User)
    return [x.to_dict() for x in user_refs]

  def list_roles(self):
    session = self.get_session()
    role_refs = session.query(Role)
    return list(role_refs)

  # These should probably be part of the high-level API
  def add_user_to_tenant(self, tenant_id, user_id):
    session = self.get_session()
    with session.begin():
      session.add(UserTenantMembership(user_id=user_id, tenant_id=tenant_id))

  def remove_user_from_tenant(self, tenant_id, user_id):
    session = self.get_session()
    membership_ref = session.query(UserTenantMembership)\
                            .filter_by(user_id=user_id)\
                            .filter_by(tenant_id=tenant_id)\
                            .first()
    with session.begin():
      session.delete(membership_ref)

  def get_tenants_for_user(self, user_id):
    session = self.get_session()
    membership_refs = session.query(UserTenantMembership)\
                      .filter_by(user_id=user_id)\
                      .all()

    return [x.tenant_id for x in membership_refs]

  def get_roles_for_user_and_tenant(self, user_id, tenant_id):
    extras_ref = self.get_extras(user_id, tenant_id)
    if not extras_ref:
      extras_ref = {}
    return extras_ref.get('roles', [])

  def add_role_to_user_and_tenant(self, user_id, tenant_id, role_id):
    extras_ref = self.get_extras(user_id, tenant_id)
    is_new = False
    if not extras_ref:
      is_new = True
      extras_ref = {}
    roles = set(extras_ref.get('roles', []))
    roles.add(role_id)
    extras_ref['roles'] = list(roles)
    if not is_new:
      self.update_extras(user_id, tenant_id, extras_ref)
    else:
      self.create_extras(user_id, tenant_id, extras_ref)

  def remove_role_from_user_and_tenant(self, user_id, tenant_id, role_id):
    extras_ref = self.get_extras(user_id, tenant_id)
    is_new = False
    if not extras_ref:
      is_new = True
      extras_ref = {}
    roles = set(extras_ref.get('roles', []))
    roles.remove(role_id)
    extras_ref['roles'] = list(roles)
    if not is_new:
      self.update_extras(user_id, tenant_id, extras_ref)
    else:
      self.create_extras(user_id, tenant_id, extras_ref)

  # CRUD
  def create_user(self, id, user):
    session = self.get_session()
    with session.begin():
      user_ref = User.from_dict(user)
      session.add(user_ref)
    return user_ref.to_dict()

  def update_user(self, id, user):
    session = self.get_session()
    with session.begin():
      user_ref = session.query(User).filter_by(id=id).first()
      old_user_dict = user_ref.to_dict()
      for k in user:
        old_user_dict[k] = user[k]
      new_user = User.from_dict(old_user_dict)

      user_ref.name = new_user.name
      user_ref.extra = new_user.extra
    return user_ref

  def delete_user(self, id):
    session = self.get_session()
    user_ref = session.query(User).filter_by(id=id).first()
    with session.begin():
      session.delete(user_ref)

  def create_tenant(self, id, tenant):
    session = self.get_session()
    with session.begin():
      tenant_ref = Tenant.from_dict(tenant)
      session.add(tenant_ref)
    return tenant_ref.to_dict()

  def update_tenant(self, id, tenant):
    session = self.get_session()
    with session.begin():
      tenant_ref = session.query(Tenant).filter_by(id=id).first()
      old_tenant_dict = tenant_ref.to_dict()
      for k in tenant:
        old_tenant_dict[k] = tenant[k]
      new_tenant = Tenant.from_dict(old_tenant_dict)

      tenant_ref.name = new_tenant.name
      tenant_ref.extra = new_tenant.extra
    return tenant_ref

  def delete_tenant(self, id):
    session = self.get_session()
    tenant_ref = session.query(Tenant).filter_by(id=id).first()
    with session.begin():
      session.delete(tenant_ref)

  def create_extras(self, user_id, tenant_id, extras):
    session = self.get_session()
    with session.begin():
      session.add(Extras(user_id=user_id, tenant_id=tenant_id, data=extras))
    return extras

  def update_extras(self, user_id, tenant_id, extras):
    session = self.get_session()
    with session.begin():
      extras_ref = session.query(Extras)\
                          .filter_by(user_id=user_id)\
                          .filter_by(tenant_id=tenant_id)\
                          .first()
      data = extras_ref.data.copy()
      for k in extras:
        data[k] = extras[k]
      extras_ref.data = data
    return extras_ref

  def delete_extras(self, user_id, tenant_id):
    self.db.delete('extras-%s-%s' % (tenant_id, user_id))
    return None

  def create_role(self, id, role):
    session = self.get_session()
    with session.begin():
      session.add(Role(**role))
    return role

  def update_role(self, id, role):
    session = self.get_session()
    with session.begin():
      role_ref = session.query(Role).filter_by(id=id).first()
      for k in role:
        role_ref[k] = role[k]
    return role_ref

  def delete_role(self, id):
    session = self.get_session()
    role_ref = session.query(Role).filter_by(id=id).first()
    with session.begin():
      session.delete(role_ref)


class SqlToken(SqlBase):
  pass


class SqlCatalog(SqlBase):
  pass
