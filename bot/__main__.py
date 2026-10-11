"""CLI: python -m bot <command>. Modules are imported per command so each workflow installs only what it needs."""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(prog="python -m bot")
    sub = parser.add_subparsers(dest="command", required=True)

    auth = sub.add_parser("auth", help="Instagram token setup and checks (see bot/auth.py)")
    auth_sub = auth.add_subparsers(dest="action", required=True)
    auth_sub.add_parser("url", help="Print the Instagram login URL")
    ex = auth_sub.add_parser("exchange", help="Trade a login code for a 60-day token")
    ex.add_argument("code")
    auth_sub.add_parser("check", help="Show the token's account and publishing quota")
    refresh = auth_sub.add_parser("refresh", help="Extend the token another 60 days")
    refresh.add_argument("--save", metavar="PATH", help="Write the new token to PATH instead of printing it (CI)")

    scrape = sub.add_parser("scrape", help="Pull a day's bookings, rank them, rebuild the queue")
    scrape.add_argument("--day", help="YYYY-MM-DD (default: yesterday, Eastern)")
    scrape.add_argument("--dry-run", action="store_true", help="Rank and print only; queue and mugshots/ untouched")

    sub.add_parser("make-reels", help="Render Reels for the unposted queue into reels/ (needs ffmpeg, pillow)")
    preview = sub.add_parser("preview-reel", help="Render one Reel from a photo, for design work")
    preview.add_argument("photo")
    preview.add_argument("--out", default="preview.mp4")
    sub.add_parser("preflight", help="Should this hour post? Prints and outputs mode= / reason=")
    post = sub.add_parser("post-next", help="Post the next queued entry")
    post.add_argument("--dry-run", action="store_true", help="Print caption and URLs; post and change nothing")
    news = sub.add_parser("news", help="News posts (see bot/news.py)")
    news_sub = news.add_subparsers(dest="action", required=True)
    news_pick = news_sub.add_parser("pick", help="Score stories, render the best, save it as pending")
    news_pick.add_argument("--dry-run", action="store_true", help="Score and render only; state untouched")
    news_pick.add_argument("--force", action="store_true", help="Ignore the news-hour and once-per-slot checks")
    news_sub.add_parser("post", help="Post the pending story")
    sub.add_parser("check-queue", help="Queue status")
    sub.add_parser("purge-unqueued", help="Delete photos no upcoming post needs")
    sub.add_parser("purge-removed", help="Strip people on the removal list from the queue and mugshots/")

    args = parser.parse_args()
    if args.command == "auth":
        from . import auth
        if args.action == "exchange":
            auth.exchange(args.code)
        elif args.action == "refresh":
            auth.refresh(args.save)
        else:
            {"url": auth.auth_url, "check": auth.check}[args.action]()
    elif args.command == "scrape":
        from . import scrape
        scrape.run(args.day, args.dry_run)
    elif args.command == "make-reels":
        from . import reels
        reels.build_queue_reels()
    elif args.command == "preview-reel":
        from . import reels
        reels.preview(args.photo, args.out)
    elif args.command == "preflight":
        from . import posting
        from .common import set_github_output
        mode, reason = posting.preflight()
        print(f"mode={mode}\nreason={reason}")
        set_github_output(mode=mode, reason=reason)
    elif args.command == "post-next":
        from . import posting
        sys.exit(0 if posting.post_next(args.dry_run) else 1)
    elif args.command == "news":
        from . import news
        if args.action == "pick":
            news.pick(args.dry_run, args.force)
        else:
            sys.exit(0 if news.post() else 1)
    elif args.command == "check-queue":
        from . import posting_queue
        posting_queue.check()
    elif args.command == "purge-unqueued":
        from . import posting_queue
        posting_queue.purge_unqueued()
    elif args.command == "purge-removed":
        from . import removals
        print(f"🧹 Removed {removals.purge()} entries for people on the removal list")


if __name__ == "__main__":
    main()
