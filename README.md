# Blog-updates experiment

# Blog Automation Script

This Python script automates the process of fetching recent articles from various RSS feeds, generating content using OpenAI's GPT model, and publishing the generated content to a Blogger blog.
Features

Fetches articles from multiple RSS feeds
Deduplicates and filters recent articles
Generates blog content using OpenAI's GPT model
Publishes generated content to a Blogger blog
Logs operations and errors
Prevents republishing of already processed articles

Prerequisites

Python 3.6+
Google Cloud Console project with Blogger API enabled
OpenAI API key
Blogger API credentials

Installation

Clone this repository
Install required packages:
Copypip install -r requirements.txt


Configuration

Create a .env file in the same directory as the script with the following content:
CopyOPENAI_API_KEY=your_openai_api_key
BLOGGER_CLIENT_SECRET_FILE=path_to_your_client_secret_file.json
BLOGGER_BLOG_ID=your_blogger_blog_id

Ensure you have the client_secret.json file for Blogger API authentication in the specified path.

Usage
Run the script with:
Copypython script_name.py
The script will:

Fetch recent articles from the specified RSS feeds
Generate content for each article using OpenAI's GPT model
Publish the generated content to your Blogger blog

Customization

Modify the RSS_FEEDS list to add or remove RSS feed sources
Adjust the filter_recent_articles function to change the time range for article selection
Modify the generate_blog_content function to customize the content generation prompt or model parameters

Logging
The script logs its operations to both a file (blog_automation.log) and the console. Check these logs for information about the script's execution and any errors encountered.
Important Notes

The script uses OAuth 2.0 for Blogger API authentication. You may need to authenticate through a browser on first run.
Token usage is logged for each content generation request to help monitor API usage.
The script maintains a list of published article links to prevent republishing.

Troubleshooting

If you encounter authentication issues, ensure your client_secret.json file is correctly set up and the Blogger API is enabled in your Google Cloud Console project.
For OpenAI API errors, verify your API key and check your usage limits.
If articles are not being fetched, check your internet connection and the validity of the RSS feed URLs.

