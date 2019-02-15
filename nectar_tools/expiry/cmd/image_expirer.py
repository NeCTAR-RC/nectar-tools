#!/usr/bin/env python

import logging
from nectar_tools.expiry.cmd import base
from nectar_tools.expiry import expirer

LOG = logging.getLogger(__name__)


class ImageExpiryCmd(base.ImageExpiryBaseCmd):

    @staticmethod
    def valid_image(image):
        # for future use, always return true for now
        return True

    @staticmethod
    def is_protected_image(image):
        return image.protected

    def get_expirer(self, image):
        return expirer.ImageExpirer(image=image,
                                    ks_session=self.session,
                                    dry_run=self.dry_run,
                                    force_delete=self.args.force_delete,
                                    force_expire=self.args.force_expire)


def main():
    cmd = ImageExpiryCmd()
    cmd.print_status()
    cmd.process_images()


if __name__ == '__main__':
    main()
