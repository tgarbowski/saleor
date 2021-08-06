from saleor.plugins.manager import get_plugins_manager


def get_dpd_config():
    manager = get_plugins_manager()
    dpd_config = manager.get_plugin('Dpd').config

    return dpd_config


def get_dpd_fid():
    dpd_config = get_dpd_config()
    return dpd_config.master_fid
