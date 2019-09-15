#!/usr/bin/env python

import argparse
import logging
import prettytable

from nectar_tools import auth
from nectar_tools import cmd_base
from nectar_tools import config
from nectar_tools import exceptions

from nectar_tools.expiry import expirer
from nectar_tools.expiry import expiry_states


CONFIG = config.CONFIG
LOG = logging.getLogger(__name__)


class ImageExpiryCmd(cmd_base.CmdBase):
    def __init__(self):
        super(ImageExpiryCmd, self).__init__(
            log_filename='image-expiry.log')

        self.g_client = auth.get_glance_client(self.session)

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

            filters = {'os_hidden': True,
                       'nectar_expiry_status': expiry_states.STOPPED}
            hidden_images = self.g_client.images.list(filters = filters)
            images.extend(list(hidden_images))

            # sort all the retrieved images by os_hidden and id
            # the hidden expiry-in-progress images will be at the bottom
            images.sort(key=lambda image: (image.os_hidden, image.id))

        else:
            LOG.error("Need to provide image id(s) or use option --all")
        self.images = images

    @staticmethod
    def valid_image(image):
        if image.visibility != 'private':
            return True
        return False

    def print_status(self):
        pt = prettytable.PrettyTable(['Name', 'Image ID', 'Status',
                                      'Hidden', 'Visibility', 'Expiry Status',
                                      'Expiry Next Step', 'Ticket ID'])
        for image in self.images:
            if self.valid_image(image):
                self.image_set_defaults(image)
                pt.add_row([image.name, image.id, image.status,
                            image.os_hidden, image.visibility,
                            image.nectar_expiry_status,
                            image.nectar_expiry_next_step,
                            image.nectar_expiry_ticket_id])
        print(pt)

    def get_expirer(self, image):
        return expirer.ImageExpirer(image=image,
                                    ks_session=self.session,
                                    dry_run=self.dry_run,
                                    force_delete=self.args.force_delete)

    @staticmethod
    def image_set_defaults(image):
        image.nectar_expiry_status = getattr(
            image, 'nectar_expiry_status', None)
        image.nectar_expiry_next_step = getattr(
            image, 'nectar_expiry_next_step', None)
        image.nectar_expiry_ticket_id = getattr(
            image, 'nectar_expiry_ticket_id', None)

    def add_args(self):
        super(ImageExpiryCmd, self).add_args()
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
                                 eligible images')
        self.parser.add_argument('-o', '--offset',
                                 type=int,
                                 default=None,
                                 help='Skip this many images \
                                 before processing')
        self.parser.add_argument('-s', '--status', action='store_true',
                                 help='Report current status of each image')
        self.parser.add_argument('-a', '--set-admin', action='store_true',
                                 help='Mark a list of projects as admins')
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

    def process_images(self):
        LOG.info("Processing images")

        limit = self.args.limit
        offset = self.args.offset
        offset_count = 0
        processed = 0

        for image in self.images:
            if self.valid_image(image):
                offset_count += 1
                if offset is None or offset_count > offset:
                    try:
                        LOG.debug("------------------")
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


def main():
    cmd = ImageExpiryCmd()
    if cmd.args.status:
        cmd.print_status()
        return
    if cmd.args.set_admin:
        cmd.set_admin()
        return
    cmd.process_images()


if __name__ == '__main__':
    main()
