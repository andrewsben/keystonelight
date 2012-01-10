

from keystone import cfg


class Config(cfg.ConfigOpts):
  def __call__(self, config_files=None, *args, **kw):
    if config_files is not None:
      self._opts['config_file']['opt'].default = config_files
    return super(Config, self).__call__(*args, **kw)

  def __getitem__(self, key, default=None):
    return getattr(self, key, default)

  def __setitem__(self, key, value):
    return setattr(self, key, value)

  def iteritems(self):
    for k in self._opts:
      yield (k, getattr(self, k))


def register_str(*args, **kw):
  group = _ensure_group(kw)
  return CONF.register_opt(cfg.StrOpt(*args, **kw), group=group)


def register_cli_str(*args, **kw):
  group = _ensure_group(kw)
  return CONF.register_cli_opt(cfg.StrOpt(*args, **kw), group=group)


def register_bool(*args, **kw):
  group = _ensure_group(kw)
  return CONF.register_opt(cfg.BoolOpt(*args, **kw), group=group)


def register_cli_bool(*args, **kw):
  group = _ensure_group(kw)
  return CONF.register_cli_opt(cfg.BoolOpt(*args, **kw), group=group)


def _ensure_group(kw):
  group = kw.pop('group', None)
  if group:
    CONF.register_group(cfg.OptGroup(name=group))
  return group



CONF = Config(project='keystone')


register_str('admin_token', default='ADMIN')
register_str('compute_port')
register_str('admin_port')
register_str('public_port')

# sql options
register_str('connection', group='sql')
register_str('idle_timeout', group='sql')
register_str('min_pool_size', group='sql')
register_str('maz_pool_size', group='sql')
register_str('pool_timeout', group='sql')

register_str('driver', group='catalog')
register_str('driver', group='identity')
register_str('driver', group='policy')
register_str('driver', group='token')
