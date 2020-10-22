from nectar_tools.audit.cmd import base
from nectar_tools.audit.image import image


class ImageAuditorCmd(base.AuditCmdBase):

    AUDITORS = [image.ImageAuditor]

    def add_args(self):
        super(ImageAuditorCmd, self).add_args()
        self.parser.description = 'Image auditor'


def main():
    cmd = ImageAuditorCmd()
    cmd.run_audits()


if __name__ == '__main__':
    main()
