import argparse
import logging
import prettytable

from nectar_tools import cmd_base
from nectar_tools import config
from nectar_tools import exceptions
from nectar_tools import utils

from nectar_tools.expiry import expiry_states


CONFIG = config.CONFIG
LOG = logging.getLogger(__name__)


class ProjectExpiryBaseCmd(cmd_base.CmdBase):

    def __init__(self):
        super(ProjectExpiryBaseCmd, self).__init__(log_filename='expiry.log')

        projects = []
        if self.args.project_id:
            project = self.k_client.projects.get(self.args.project_id)
            projects.append(project)
        elif self.args.all or self.args.filename:
            projects = self.k_client.projects.list(enabled=True,
                                                   domain=self.args.domain)
            if self.args.filename:
                wanted_projects = utils.read_file(self.args.filename)

                projects = [p for p in projects if p.id in wanted_projects]
            projects.sort(key=lambda p: p.name.split('-')[-1].zfill(5))
        self.projects = projects

    def print_status(self):
        pt = prettytable.PrettyTable(['Name', 'Project ID', 'Status',
                                      'Expiry date', 'Ticket ID'])
        for project in self.projects:
            if self.valid_project(project):
                self.project_set_defaults(project)
                pt.add_row([project.name, project.id,
                            project.expiry_status, project.expiry_next_step,
                            project.expiry_ticket_id])
        print(pt)

    def pre_process_projects(self):
        return

    def process_projects(self):
        LOG.info("Processing projects")
        self.pre_process_projects()

        limit = self.args.limit
        offset = self.args.offset
        offset_count = 0
        processed = 0

        for p in self.projects:
            if self.valid_project(p):
                offset_count += 1
                if offset is None or offset_count > offset:
                    try:
                        ex = self.get_expirer(p)
                        if ex.process():
                            processed += 1
                    except exceptions.InvalidProject:
                        pass
                    except Exception:
                        LOG.exception('Exception processing project %s', p.id)

                if limit > 0 and processed >= limit:
                    break
        LOG.info("Processed %s projects", processed)
        return processed

    def add_args(self):
        """Handle command-line options"""
        super(ProjectExpiryBaseCmd, self).add_args()
        self.parser.description = 'Updates project expiry date'
        project_group = self.parser.add_mutually_exclusive_group()
        project_group.add_argument('-f', '--filename',
                            type=argparse.FileType('r'),
                            help='File path with a list of project IDs, \
                                 one on each line')
        self.parser.add_argument('-l', '--limit',
                            type=int,
                            default=0,
                            help='Only process this many eligible projects.')
        self.parser.add_argument('-o', '--offset',
                            type=int,
                            default=None,
                            help='Skip this many projects before processing.')
        project_group.add_argument('--all', action='store_true',
                            help='Run over all projects')
        project_group.add_argument('-p', '--project-id',
                            help='Project ID to process')
        self.parser.add_argument('--domain', default='default',
                            help='Project domain.')
        self.parser.add_argument('-s', '--status', action='store_true',
                            help='Report current status of each project.')
        self.parser.add_argument('-a', '--set-admin', action='store_true',
                            help='Mark a list of projects as admins')
        self.parser.add_argument('--action-state', action='store',
                            default=None,
                            help='Only process projects in this state')
        self.parser.add_argument('--force-delete', action='store_true',
                            help="Delete a project no matter what state it's \
                                 in")

    @staticmethod
    def project_set_defaults(project):
        project.owner = getattr(project, 'owner', None)
        project.expiry_status = getattr(project, 'expiry_status', None)
        project.expiry_next_step = getattr(project, 'expiry_next_step', None)
        project.expiry_ticket_id = getattr(project, 'expiry_ticket_id', None)

    def set_admin(self):
        """Set status to admin for specified list of projects.
        """
        for project in self.projects:
            self.project_set_defaults(project)
            if project.expiry_status == expiry_states.ADMIN:
                LOG.error("Project %s is already admin", project.id)
            else:
                if self.dry_run:
                    LOG.info("would set status admin for %s(%s) (dry run)",
                             project.name, project.id)
                else:
                    LOG.debug("setting status admin for %s", project.id)
                    self.k_client.projects.update(
                        project.id, expiry_status=expiry_states.ADMIN)


class ImageExpiryBaseCmd(cmd_base.CmdBase):
    def __init__(self):
        super(ImageExpiryBaseCmd, self).__init__(
            log_filename='image_expiry.log')

        images = []
        if self.args.image_id:
            image = self.g_client.images.get(self.args.image_id)
            images.append(image)
        elif self.args.all or self.args.filename:
            for visibility in ['public', 'shared', 'community']:
                shared_images = self.g_client.images.list(
                    filters = {'visibility': visibility})
                images.extend(shared_images)

            if self.args.filename:
                wanted_images = self.read_file(self.args.filename)
                images = [i for i in images if i.id in wanted_images]
            images.sort(key=lambda image: image.id)

            filters = {'visibility': 'private',
                       'nectar_expiry_status': 'RESTRICTED'}
            private_images = self.g_client.images.list(filters = filters)
            images.extend(list(private_images))
        else:
            LOG.error("Need to provide image id(s) or use option --all")
        self.images = images

    def print_status(self):
        pt = prettytable.PrettyTable(['Name', 'Image ID', 'Status',
                                      'Visibility', 'Expiry Status',
                                      'Expiry Next Step', 'Ticket ID'])
        for image in self.images:
            if self.valid_image(image):
                self.image_set_defaults(image)
                pt.add_row([image.name, image.id, image.status,
                            image.visibility, image.nectar_expiry_status,
                            image.nectar_expiry_next_step,
                            image.nectar_expiry_ticket_id])
        print(pt)

    @staticmethod
    def image_set_defaults(image):
        image.nectar_expiry_status = getattr(
            image, 'nectar_expiry_status', None)
        image.nectar_expiry_next_step = getattr(
            image, 'nectar_expiry_next_step', None)
        image.nectar_expiry_ticket_id = getattr(
            image, 'nectar_expiry_ticket_id', None)

    def add_args(self):
        super(ImageExpiryBaseCmd, self).add_args()
        self.parser.description = 'Updates non-private image expiry date'
        image_group = self.parser.add_mutually_exclusive_group()
        image_group.add_argument('-f', '--filename',
                                 type=argparse.FileType('r'),
                                 help='File path with a list of image IDs, \
                                 one on each line')
        image_group.add_argument('-i', '--image-id',
                                 help='Image ID to process')
        image_group.add_argument('--all', action='store_true',
                                 help='Run over all images')
        self.parser.add_argument('-l', '--limit',
                                 type=int,
                                 default=0,
                                 help='Only process this many \
                                 eligible images.')
        self.parser.add_argument('-o', '--offset',
                                 type=int,
                                 default=None,
                                 help='Skip this many images \
                                 before processing.')
        self.parser.add_argument('-s', '--status', action='store_true',
                                 help='Report current status of each image.')
        self.parser.add_argument('-a', '--set-admin', action='store_true',
                                 help='Mark a list of projects as admins')
        self.parser.add_argument('--action-state', action='store',
                                 default=None,
                                 help='Only process images in this state')
        self.parser.add_argument('--force-delete', action='store_true',
                                 help="Delete an image no matter what state it's \
                                 in")

    def set_admin(self):
        """Set status to admin for specified list of images.
        """
        for image in self.images:
            self.image_set_defaults(image)
            if image.nectar_expiry_status == expiry_states.ADMIN:
                LOG.error("Image %s is already admin", image.id)
            else:
                if self.dry_run:
                    LOG.info("would set status admin for %s(%s) (dry run)",
                             image.name, image.id)
                else:
                    LOG.debug("setting status admin for %s", image.id)
                    self.g_client.images.update(
                        image.id, nectar_expiry_status=expiry_states.ADMIN)

    def pre_process_images(self):
        return

    def process_images(self):
        LOG.info("Processing images")
        self.pre_process_images()

        limit = self.args.limit
        offset = self.args.offset
        offset_count = 0
        processed = 0

        for image in self.images:
            if self.valid_image(image):
                offset_count += 1
                if offset is None or offset_count > offset:
                    try:
                        ex = self.get_expirer(image)
                        if ex.process():
                            processed += 1
                    except exceptions.InvalidImage:
                        pass
                    except Exception:
                        LOG.exception('Exception processing Image %s',
                                      image.id)
                if limit > 0 and processed >= limit:
                    break
        LOG.info("Processed %s images", processed)
        return processed
