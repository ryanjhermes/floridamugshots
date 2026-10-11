# Meta app setup (Instagram API with Instagram Login)

One-time setup for @florida.mugshots. We use **Instagram Login** (`graph.instagram.com`), so no Facebook Page
is needed. This app is new and separate from the Minneapolis app, so neither account can break the other.

## 1. Convert the Instagram account (phone app, 2 min)

1. Log in as **florida.mugshots** → Settings → *Account type and tools* → **Switch to professional account**.
2. Pick **Business** (not Creator). Category: *News & Media Website* or *Media/News Company*.
3. Skip connecting a Facebook Page. Instagram Login doesn't need one.
4. Fill in the bio now (see "Bio" below). Reviewers and users both look at it.

## 2. Create the Meta app

1. [developers.facebook.com/apps](https://developers.facebook.com/apps) → **Create app**.
2. Name: `Florida Mugshots Bot`. Use case: **Manage messaging & content on Instagram**.
3. Business portfolio: skip for now (it's only required later for Advanced Access).
4. Settings → Basic: add a **Privacy Policy URL** and **Terms URL**. The app can't go Live without them. A
   simple page will do for now (it can live on the Pages site we'll set up later).

## 3. Connect the account and get a token

Dashboard → **Customize the Manage messaging & content on Instagram use case** → **API setup with Instagram
login** (not "with Facebook login"; ignore the Facebook Login for Business sidebar item and "Become a Tech
Provider"):

1. Note the **Instagram app ID** and **Instagram app secret** in that section. These are *not* the Meta App ID
   at the top of the dashboard. Put them in `.env` as `IG_APP_ID` and `IG_APP_SECRET` (copy `.env.example`).
2. **Generate access tokens** → *Add account* → log in as florida.mugshots → approve every permission. Then
   copy the token into `.env` as `IG_ACCESS_TOKEN`. This token is already long-lived (60 days).
3. Turn on **webhooks/messages** later, when we build DM handling. They aren't needed to post.

If the dashboard won't generate a token, use OAuth instead:

1. Under **Business login settings**, add `https://ryanhermes.com/` as a redirect URI.
2. Run `python -m bot auth url`, open the link, approve, and copy `code=` from the address bar.
3. Run `python -m bot auth exchange <code>`, then paste its output into `.env`.

## 4. Verify

```bash
cd floridamugshots
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
python -m bot auth check
```

Expected: `✅ @florida.mugshots (BUSINESS), user_id …`. Copy the `user_id` into `IG_USER_ID`. You should also
see a publishing quota line (`0/100`). If it says `MEDIA_CREATOR` or `PERSONAL`, step 1 didn't take.

## 5. Access level: Standard vs Advanced

In **Standard Access** (no review), the API works only for accounts that have a role on the app. That covers
everything we're doing, since the bot posts only to our own account and reads only its own DMs. **Advanced
Access / App Review isn't needed** unless the app later serves other people's accounts. The app does need to
be **Live** (toggle at the top) for DMs from the public to come through.

## 6. Token upkeep

Long-lived tokens last 60 days, and an expired token can't be refreshed (you'd have to redo step 3).
`python -m bot auth refresh` extends the token. We'll automate this on a weekly schedule when the workflows
exist, which means the job has to write the new token back to the repo secret.

## Bio (draft)

> Florida public booking records. Arrest ≠ conviction; everyone is presumed innocent.
> Want a post removed? DM us. Removal is always free.
