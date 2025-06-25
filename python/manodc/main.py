"""Main module for manodc NSO package."""

import multiprocessing

import ncs

from . import actions, background_process, manodc_workers, services, validations


class Main(ncs.application.Application):
    """Manodc main class."""
    nreader = None
    worker = None

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

        self.register_action(actionpoint="parse-csv", action_cls=actions.ParseCsv)

        self.register_action(actionpoint="manodc-notification-actionpoint", action_cls=actions.SendNotification)

        self.register_action(actionpoint="manodc-allocate-ids", action_cls=actions.AllocateIds)

        self.register_validation("gateway-valpoint", validations.GatewayValidationCallback)  # pylint: disable=no-member

        qbuf = multiprocessing.Manager().Queue()
        self.nreader = background_process.Process(self,
                                                  manodc_workers.notif_reader, (qbuf, ),
                                                  config_path="/manodc:manodc-bgworkers/enabled",
                                                  run_during_upgrade=True)
        self.worker = background_process.Process(self,
                                                 manodc_workers.plan_handler, (qbuf, ),
                                                 config_path="/manodc:manodc-bgworkers/enabled",
                                                 run_during_upgrade=True)
        self.nreader.start()
        self.worker.start()

    def teardown(self):
        """Teardown service and actions."""
        self.nreader.stop()
        self.worker.stop()
        self.log.info("Main FINISHED")
