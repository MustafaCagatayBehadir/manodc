"""Data manipulation callback module."""
import _ncs
import ncs


class DpApi:
    """Data manipulation callback interface."""

    def __init__(self, call_point: str, log: ncs.log.Log) -> None:
        self.log = log
        self.daemon = ncs.dp.Daemon(call_point)
        _ncs.dp.register_data_cb(self.daemon.ctx(), call_point, self)
        self.daemon.start()
        self.log.info("DpApi: ", call_point, " started")

    def get_root(self, tctx) -> ncs.maagic.Root:
        """Get root node."""
        _maapi = ncs.maapi.Maapi()
        trans = _maapi.attach(tctx)
        root = ncs.maagic.get_root(trans)
        return root

    def cb_create(self, tctx, kp):
        """Create node callback."""
        self.log.info("cb_create: ", kp)
        root = self.get_root(tctx)
        site = ncs.maagic.cd(root, kp)
        site.site_name = f"{site.location}-{site.hall}-{site.fabric}"
