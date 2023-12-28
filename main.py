# -----------------------------------------------------------
# Script that every day at a specific time will look for papers 
# from the same day in ArXiv of the selected archive, create a 
# markdown file and send a Slack message with a digest. 
#
# The script will recognize relevant papers based on a list 
# of authors and keywords with an associated weight, if the 
# combined weight of all matches surpasses a certain threshold 
# the paper will be flagged as relevant.
#
# (C) 2023 Quantronics Group, Paris
# Released under GNU Public License (GPL)
# email jaimetravesedo125@gmail.com
# -----------------------------------------------------------

from bs4 import BeautifulSoup
from time import sleep
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import requests, yaml, datetime, schedule, logging, os

with open("config.yaml", 'r', encoding='utf-8') as f:
    CONFIG = yaml.load(f, Loader=yaml.Loader)  


logging.basicConfig(filename=CONFIG['logging_file'], encoding='utf-8', level=logging.DEBUG)


def load_keywords() -> dict:
    """Function that loads a csv with structure 'keyword, int\n' and saves them as a dict"""
    filename = CONFIG["keywords_file"]
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            all_keywords = yaml.load(f, Loader=yaml.Loader)
    except Exception as e:
        logging.warning('Error when opening the keyword file: ', e)
        logging.info('Loading backup')
        with open('keywords.backup', 'r', encoding='utf-8') as f:
            all_keywords = yaml.load(f, Loader=yaml.Loader)
    
    # After succesfully loading create a backup
    with open('keywords.backup', 'w', encoding='utf-8') as f:
        yaml.dump(all_keywords, f)
    return all_keywords


def send_slack_message(filename: str):
    with open(filename, 'r', encoding='utf-8') as f:
        msg = f.read()

    client = WebClient(os.environ['SLACK_BOT_TOKEN'])
    try:
        response = client.chat_postMessage(channel=CONFIG['slack_channel'], text=msg, mrkdwn=True, unfurl_links=False, unfurl_media=False)
    except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
        assert e.response["ok"] is False
        assert e.response["error"]  # str like 'invalid_auth', 'channel_not_found'
        logging.error(f"Got an error: {e.response['error']}")
        # Also receive a corresponding status_code
        assert isinstance(e.response.status_code, int)
        logging.error(f"Received a response status_code: {e.response.status_code}")


class Paper:
    """
    Dataclass to manage the relevant information of each paper.
    All information is parsed from the input html data.
    """
    AUTHORS = {}
    KEYWORDS = {}

    def __init__(self, reference: str, soup: BeautifulSoup) -> None:
        self.reference = reference

        # Get title and authors removing superfluous information
        self.title = soup.find('div', class_="list-title mathjax").get_text()[8:-1]
        self.authors = soup.find('div', class_="list-authors").get_text()[10:-1].split(', \n')
        self.abstract = soup.find('p', class_="mathjax").get_text()

        # Parse the title for keywords and the author for relevant authors
        self.kw_match = self.get_kw_matches(self.title, self.KEYWORDS)
        self.author_match = self.get_kw_matches(' '.join(self.authors), self.AUTHORS)
        print(self.author_match)
        self.weight = 0
        for kw in self.kw_match: self.weight += self.KEYWORDS[kw]
        for kw in self.author_match: self.weight += self.AUTHORS[kw]

        # Paper is relevant if there is any match
        self.is_relevant = self.weight>=CONFIG["threshold"]

    def get_md_text(self, abstract) -> str:
        # Only print the number of authors if the list is larger than 10 authors
        print_authors = self.authors
        if len(self.authors)>10:
            print_authors = self.authors[:9]
            print_authors.append(self.authors[-1])

        # Get a markdown summary of the paper
        md_list = [
            f'## **[{self.title}](https://arxiv.org/abs/{self.reference})**',
            f'### _Authors: {", ".join(print_authors)}_',
            f'#### 🗝️**Keywords**: {", ".join(self.kw_match)}, {", ".join(self.author_match)}'
        ]
        if abstract: md_list.append(self.abstract)

        return '\n\n'.join(md_list)

    def get_mrkdwn_text(self, abstract) -> str:
        # Make a reduced list of authors
        print_authors = self.authors[:9]
        if len(self.authors)>9:
            print_authors.append('...')
            print_authors.append(self.authors[-1])

        # Get a markdown summary of the paper
        md_list = [
            f'<https://arxiv.org/abs/{self.reference}|*{self.title}*>',
            f'Authors: {", ".join(print_authors)}',
            f'🗝️ _Keywords: {", ".join(self.kw_match)}, {", ".join(self.author_match)}_'
        ]
        if abstract: md_list.append(self.abstract)

        return '\n\n'.join(md_list)

    def get_kw_matches(self, phrase: str, keyword_list: list) -> list:
        matches = []
        for keyword in keyword_list:
            if keyword.lower() in phrase.lower():
                matches.append(keyword)
        return matches


def write_summary():
    # Reload the keywords in case there is an update
    all_keywords = load_keywords()
    Paper.KEYWORDS = all_keywords['keywords']
    Paper.AUTHORS = all_keywords['authors']

    # Send a request to ArXiv for yesterdays papers
    yesterday = datetime.date.today() - datetime.timedelta(days=0)
    if yesterday.weekday() >= 5:
        logging.info("No papers during the weekend")
        return 0
    
    payload = {
        "MIME Type": "application/x-www-form-urlencoded",
        "archive": CONFIG["archive"],
        "sday": yesterday.day,
        "smonth": yesterday.month,
        "syear": yesterday.year,
        "method": "with"
    }
    r = requests.get("https://arxiv.org/catchup", params=payload)
    try:
        soup_yesterday = BeautifulSoup(r.text, features="html.parser").find('h2').findNext('dl')
    except AttributeError:
        error_file = f'summaries/error_{yesterday.day}_{yesterday.month}_{yesterday.year}.html'
        with open(error_file, 'w') as f: f.write(r.text)
        logging.warning(f'No papers were found today, check html file saved at {error_file}')
        return 1
    
    # Get the references of the paper and create a Paper object for each one of them. 
    # Then if the paper is relevant add an entry to the markdown list
    papers = []
    md_list = ["📰 *Today's Relevant Papers*"]
    for soup_paper, soup_links in zip(soup_yesterday.find_all('div', class_='meta'), soup_yesterday.find_all('span', class_='list-identifier')):
        ref = soup_links.find('a')['href'][5:]
        p = Paper(ref, soup_paper)
        papers.append(p)
        if not p.is_relevant: continue
        md_list.append(p.get_mrkdwn_text(CONFIG["include_abstract"]))
    
    # Save the markdown
    if not os.path.exists('summaries'): os.makedirs('summaries')
    md_text = '\n\n-----------------------\n\n'.join(md_list)
    md_file = f"summaries/{yesterday.day}_{yesterday.month}_{yesterday.year}.md"
    with open(md_file, "w", encoding='utf-8') as f:
        f.write(md_text)
    
    logging.info(f"Found {len(papers)} relevant papers.")
    logging.info(f"Markdown file was saved at {md_file}")

    send_slack_message(md_file)
    return 0

if __name__ == "__main__":
    write_summary()
    schedule.every().day.at(CONFIG['post_hour']).do(write_summary)
    while True:
        schedule.run_pending()
        sleep(60)