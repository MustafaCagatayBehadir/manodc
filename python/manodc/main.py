"""Main module for manodc NSO package."""

import ncs

from . import services


class Main(ncs.application.Application):
    """Manodc main class."""

    def setup(self):
        """Register services and actions."""
        self.log.info("Main RUNNING")

        self.register_nano_service(servicepoint="bridge-domain-vlan-servicepoint",
                                   componenttype="ncs:self",
                                   state="manodc:id-allocated",
                                   nano_service_cls=services.BdVlanServiceCallback)

        self.register_nano_service(servicepoint="bridge-domain-vlan-servicepoint",
                                   componenttype="manodc:vlan-endpoint",
                                   state="manodc:vlan-configured",
                                   nano_service_cls=services.BdVlanServiceCallback)

        self.register_nano_service(servicepoint="bridge-domain-vlan-switch-servicepoint",
                                   componenttype="ncs:self",
                                   state="manodc:vlan-switch-configured",
                                   nano_service_cls=services.BdVlanSwitchServiceCallback)

    def teardown(self):
        """Teardown service and actions."""
        self.log.info('Main FINISHED')
