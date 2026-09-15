from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = (
        "Run chatbot and/or marketing-content evaluation. "
        "Does not run automatically at startup."
    )

    def add_arguments(self, parser):
        parser.add_argument("--chatbot-only", action="store_true")
        parser.add_argument("--content-only", action="store_true")
        parser.add_argument("--dataset", default=None)
        parser.add_argument("--output-dir", default=None)

    def handle(self, *args, **options):
        extra = {}
        if options.get("output_dir"):
            extra["output_dir"] = options["output_dir"]
        run_chatbot = not options["content_only"]
        run_content = not options["chatbot_only"]
        if options["chatbot_only"] and options["content_only"]:
            run_chatbot = True
            run_content = True
        if run_chatbot:
            chatbot_opts = dict(extra)
            if options.get("dataset") and options["chatbot_only"]:
                chatbot_opts["dataset"] = options["dataset"]
            call_command("evaluate_chatbot", **chatbot_opts)
        if run_content:
            content_opts = dict(extra)
            if options.get("dataset") and options["content_only"]:
                content_opts["dataset"] = options["dataset"]
            call_command("evaluate_content", **content_opts)
