# botXiv

**botXiv** is a small Python script that scrapes the latest papers from an *ArXive*'s predefined archive and posts a Slack message every day with a digest of the relevant articles. Relevance is achieved by matching titles or authors with a list of used defined keywords with an associated weight, if the sum of the weights of all mathches is larger than a user defined threshold the article is flagged as relevant.  

In order to run it you must first download the script and install the required dependencies in a new environment:

```
git clone https://github.com/arzdou/botXiv.git
pip install -r botVix/requirements.txt
```

Create a keyword file using the same format as `keywords.txt` and point the script to said file using the config file.

Finally, create an environment variable for your Bot User OAuth Token from your [Slack App](https://api.slack.com/start#creating) and run the script

```
export SLACK_BOT_TOKEN=xoxb-(the_rest_of_your_token)
python botXiv/main.py
```

