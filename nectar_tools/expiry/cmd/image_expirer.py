#!/usr/bin/env python

from nectar_tools.expiry.cmd import base
from nectar_tools.expiry import expirer


class ImageExpiryCmd(base.ImageExpiryCmd):

    @staticmethod
    def valid_image(image):
        if image.visibility != 'private':
            return True
        return False

    def get_expirer(self, image):
        return expirer.ImageExpirer(image=image,
                                    ks_session=self.session,
                                    dry_run=self.dry_run,
                                    force_delete=self.args.force_delete)


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
