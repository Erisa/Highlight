# Highlight Bot Privacy Policy

This document is the Privacy Policy for the bot called Highlight and operated by Erisa.

If you have questions about this policy or the contents therein, please contact Erisa directly at privacy@erisa.uk or https://erisa.uk/contact 

If you wish to opt out of data processing or exclude yourself from your content being tracked by the bot in a Discord server that both you and the bot are in, please contact Erisa directly at privacy@erisa.uk or https://erisa.uk/contact . To verify the request, you will then be asked to send a message on Discord. Deletion requests will be handled within 30 days.

Highlight processes some data from Discord, and stores some user provided data.

The following data is stored by the bot:
- The provided highlight words that a user has submitted, keyed against the ID of their user and the Discord server it was created in. These can be deleted through the bot by the user.
- The user's personal settings or preferences set through the bot.
- A list of each time that a highlight word has been triggered. The server ID, channel ID, message ID, invoked word and the time it happened, stored alongside the ID of the user who wrote the message and the user receiving the notification. The full contents of the message is not stored.
- A list of active timers for timed `disable` commands.

The following data is processed by the bot in-memory and is not stored:
- Message content of messages in servers that the bot is in. These are checked for any highlight words, optionally used to build a notification embed for a user and then evicted from memory.
- Information about the current state of members in servers the bot is in, such as usernames and avatars, used to populate embeds and to check which members are in which servers.

Message content or information about Discord users beyond their unique IDs and preferences is not persistently stored by the bot.

Highlight words and settings are stored until you delete them through the bot or request deletion. The notification log is retained until a deletion request is received.

Data is stored and processed by Hetzner servers in Falkenstein, Germany.
