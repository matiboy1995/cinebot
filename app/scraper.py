# app/scraper.py

import requests
from bs4 import BeautifulSoup, Tag
import json
import os
import re
import logging
from datetime import datetime

# -----------------------------------------
# Config
# -----------------------------------------
CURRENT_YEAR = datetime.now().year
HEADERS = {"User-Agent": "Mozilla/5.0"}
VENUE = "Prince Charles Cinema"
URL = "https://princecharlescinema.com/whats-on/"

# -----------------------------------------
# Utility: Parse Date (from heading)
# -----------------------------------------
def parse_pcc_date(date_str):
    """
    Parses PCC date ('Thursday 3rd April') assuming the current year.
    Removes ordinal suffixes (st, nd, rd, th) before parsing.
    Tries next year if the parsed date seems too far in the past.
    """
    logging.debug(f"Attempting to parse PCC date: '{date_str}'")
    if not date_str:
        logging.warning("Received empty PCC date string for parsing.")
        return None
    try:
        cleaned_date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str.strip())
        date_str_with_year = f"{cleaned_date_str} {CURRENT_YEAR}"
        parsed_dt = datetime.strptime(date_str_with_year, '%A %d %B %Y')

        if (datetime.now().date() - parsed_dt.date()).days > 60:
            date_str_with_year = f"{cleaned_date_str} {CURRENT_YEAR + 1}"
            parsed_dt = datetime.strptime(date_str_with_year, '%A %d %B %Y')
            logging.debug(f"Parsed PCC date '{date_str}' seemed past, interpreting as next year: {parsed_dt.date()}")
        else:
            logging.debug(f"Parsed PCC date '{date_str_with_year}' to {parsed_dt.date()}")

        return parsed_dt.date()

    except ValueError as e:
        logging.error(f"Error parsing PCC date string '{date_str}' (cleaned: '{cleaned_date_str}') with year {CURRENT_YEAR} (or +1): {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error in parse_pcc_date for '{date_str}': {e}")
        return None


# -----------------------------------------
# Utility: Parse Time (from span.time)
# -----------------------------------------
def parse_pcc_time(time_str):
    """Parses PCC time ('12:00 pm') and converts to HH:MM (24-hour) format."""
    logging.debug(f"Attempting to parse PCC time: '{time_str}'")
    if not time_str:
        logging.warning("Received empty PCC time string for parsing.")
        return None
    try:
        parsed_time_obj = datetime.strptime(time_str.lower(), '%I:%M %p')
        formatted_time = parsed_time_obj.strftime('%H:%M')
        logging.debug(f"Parsed PCC time '{time_str}' to '{formatted_time}'")
        return formatted_time
    except ValueError as e:
        logging.error(f"Error parsing PCC time string '{time_str}': {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error in parse_pcc_time for '{time_str}': {e}")
        return None


# -----------------------------------------
# Main Scraper Function
# -----------------------------------------
def scrape_pcc():
    """Scrapes screening data from Prince Charles Cinema website."""
    logging.info(f"Starting scrape for {VENUE} at {URL}")
    screenings = []

    try:
        response = requests.get(URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        film_containers = soup.find_all('div', class_=lambda c_list:
            c_list and 'jacro-event' in c_list and 'movie-tabs' in c_list and 'row' in c_list
        )

        if not film_containers:
            logging.error(f"{VENUE}: Could not find film containers. Check website structure.")
            return screenings

        logging.info(f"{VENUE}: Found {len(film_containers)} potential film entries.")
        processed_count = 0
        skipped_count = 0

        for container in film_containers:
            title_anchor = container.find('a', class_='liveeventtitle')
            film_title = title_anchor.text.strip() if title_anchor else None

            if not film_title:
                logging.warning(f"{VENUE}: Skipping container - no film title.")
                skipped_count += 1
                continue

            perf_list = container.find('ul', class_='performance-list-items')
            if not perf_list:
                logging.debug(f"{VENUE}: No screenings list found for '{film_title}'.")
                skipped_count += 1
                continue

            processed_count += 1
            found_screenings_for_film = 0
            current_date = None

            for child in perf_list.children:
                if not isinstance(child, Tag):
                    continue

                if child.name == 'div' and 'heading' in child.get('class', []):
                    date_str_raw = child.text.strip()
                    current_date = parse_pcc_date(date_str_raw)
                    if not current_date:
                        logging.warning(f"{VENUE}: Failed to parse date heading '{date_str_raw}' for '{film_title}'.")
                    continue

                if child.name == 'li':
                    if not current_date:
                        logging.warning(f"{VENUE}: Found time (li) with no preceding date for '{film_title}'.")
                        continue

                    time_span = child.find('span', class_='time')
                    if not time_span:
                        logging.warning(f"{VENUE}: No 'span.time' found for '{film_title}' on {current_date}.")
                        continue

                    time_str_raw = time_span.text.strip()
                    parsed_time_str = parse_pcc_time(time_str_raw)

                    if parsed_time_str:
                        screenings.append({
                            'Venue': VENUE,
                            'Film': film_title,
                            'Date': str(current_date),
                            'Time': parsed_time_str
                        })
                        found_screenings_for_film += 1

            if found_screenings_for_film == 0:
                logging.info(f"{VENUE}: Processed '{film_title}', but no valid screenings extracted.")

    except requests.exceptions.RequestException as e:
        logging.error(f"{VENUE}: NETWORK ERROR: {e}")
    except Exception as e:
        logging.exception(f"{VENUE}: Unexpected error.")

    logging.info(f"{VENUE}: Finished. {processed_count} processed, {skipped_count} skipped. {len(screenings)} screenings extracted.")
    return screenings


# -----------------------------------------
# Save JSON Output
# -----------------------------------------
def save_showtimes(data, filename="data/showtimes_pcc.json"):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# -----------------------------------------
# Run from CLI
# -----------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("📽️  Scraping Prince Charles Cinema...\n")
    data = scrape_pcc()
    save_showtimes(data)
    print(f"\n✅ Done. Saved {len(data)} screenings to data/showtimes_pcc.json.")
