import io
import os
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from wise import WiseApi

pd.set_option("display.max_rows", None)
pd.set_option("display.max_columns", None)

APP_TITLE = "Wise Statements"
MAIN_PAGE_HEADER = "Displays Euro business accounts."
CURRENT_YEAR = datetime.now().year
SELECTED_ACCOUNT_TYPE = "BUSINESS"
CURRENCY = "EUR"

PAGE_STANDARD = "Standard account statement"
PAGE_JAR = "Jar account statement"
PAGE_METADATA = "Metadata"
PAGE_CASHBACK = "Cashback statement"

ALL_PAGES = [
    PAGE_STANDARD,
    PAGE_JAR,
    PAGE_CASHBACK,
    PAGE_METADATA,
]

st.set_page_config(page_title=APP_TITLE, page_icon=":euro:")


def main() -> None:
    """
    Main function to run the Streamlit web application using the WiseApi class.
    """
    st.title(APP_TITLE)
    st.header(MAIN_PAGE_HEADER)
    st.info("Displays Euro accounts.")

    sandbox_checkbox = st.sidebar.checkbox("Sandbox account")

    wise_api_token = os.getenv("WISE_API_TOKEN")
    if not wise_api_token:
        wise_api_token = st.sidebar.text_input("Enter Wise API token:", type="password")

    private_key_file = st.sidebar.file_uploader(
        "Upload private key file", type=["pem", "key", "txt", "cer", "cert"]
    )
    if not private_key_file:
        return
    private_key_bytes = private_key_file.getvalue()

    try:
        wise_session = WiseApi(
            api_token=wise_api_token,
            private_key_bytes=private_key_bytes,
            use_sandbox=sandbox_checkbox,
        )
    except ValueError as e:
        st.error(f"Failed to create Wise session: {e}")
        return

    try:
        profile_data_list = wise_session.get_profile_data(
            selected_account_type=SELECTED_ACCOUNT_TYPE
        )
        if len(profile_data_list) > 1:
            st.write(
                "More than one business account found. The first account is displayed."
            )
        profile_data = profile_data_list[0]
        profile_id = profile_data["id"]
    except ValueError as e:
        st.error(f"Failed to get profile data: {e}")
        return

    selected_page = st.sidebar.radio(
        "Select page",
        ALL_PAGES,
        index=0,
    )
    if selected_page in [PAGE_STANDARD, PAGE_JAR, PAGE_CASHBACK]:
        (
            start_date,
            end_date,
        ) = get_date_range()
        if not start_date or not end_date:
            return
    try:
        standard_balance, standard_balance_id = wise_session.get_eur_balance_dict(
            profile_id=profile_id, currency=CURRENCY
        )
    except ValueError as e:
        st.error(f"Error getting standard balance. {e}")
        return
    if not standard_balance or not standard_balance_id:
        return
    try:
        jar_balances, jar_balance_id = wise_session.get_eur_balance_dict(
            profile_id=profile_id, currency=CURRENCY, jar=True
        )
    except ValueError as e:
        st.error(f"Error getting jar balance. {e}")
        jar_balances = None

    if selected_page == PAGE_STANDARD:
        try:
            standard_statement_df = wise_session.get_statement_df(
                profile_id=profile_id,
                balance_id=standard_balance_id,  # type: ignore
                start_date=start_date,  # type: ignore
                end_date=end_date,  # type: ignore
            )
            standard_statement_df["Date"] = pd.to_datetime(
                standard_statement_df["Date"], format="%d-%m-%Y"
            )
            standard_statement_df["Date"] = standard_statement_df["Date"].dt.strftime(
                "%d.%m.%Y"
            )
            show_page_statement(
                statement_df=standard_statement_df,
                profile_id=profile_id,
                start_date=start_date,  # type: ignore
                end_date=end_date,  # type: ignore
                standard_jar_or_cashback="Standard",
                selected_account_type=SELECTED_ACCOUNT_TYPE,
            )

        except ValueError as e:
            st.error(f"Error: {e}")

    elif selected_page == PAGE_JAR:
        if not jar_balances:
            st.write("No Jar account balances found.")
            return
        try:
            jar_statement_df = wise_session.get_statement_df(
                profile_id=profile_id,
                balance_id=jar_balance_id,  # type: ignore
                start_date=start_date,  # type: ignore
                end_date=end_date,  # type: ignore
            )
            jar_statement_df["Date"] = pd.to_datetime(
                jar_statement_df["Date"], format="%d-%m-%Y"
            )
            jar_statement_df["Date"] = jar_statement_df["Date"].dt.strftime("%d.%m.%Y")
            show_page_statement(
                statement_df=jar_statement_df,
                profile_id=profile_id,
                start_date=start_date,  # type: ignore
                end_date=end_date,  # type: ignore
                standard_jar_or_cashback="Jar",
                selected_account_type=SELECTED_ACCOUNT_TYPE,
            )

        except ValueError as e:
            st.error(f"Error: {e}")

    elif selected_page == PAGE_CASHBACK:
        try:
            cashback_df = wise_session.get_cashback_df(
                profile_id=profile_id,
                start_date=start_date,  # type: ignore
                end_date=end_date,  # type: ignore
            )

            show_page_statement(
                statement_df=cashback_df,
                profile_id=profile_id,
                start_date=start_date,  # type: ignore
                end_date=end_date,  # type: ignore
                standard_jar_or_cashback="Cashback",
                selected_account_type=SELECTED_ACCOUNT_TYPE,
            )
        except ValueError as e:
            st.error(f"Error processing or fetching cashback: {e}")
    elif selected_page == PAGE_METADATA:
        show_page_metadata(profile_data, standard_balance, jar_balances)


def convert_dataframe_to_excel(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return buffer.getvalue()


def get_date_range() -> tuple[date | None, date | None]:
    one_month_ago = (datetime.now() - timedelta(days=30)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_date_default = datetime.now()
    start_date = st.date_input("Start date:", one_month_ago)
    end_date = st.date_input("End date:", end_date_default)
    if not start_date <= end_date:  # type: ignore
        st.error("Start date must be before end date.")
        return None, None
    return start_date, end_date  # type: ignore


def show_page_statement(
    statement_df: pd.DataFrame,
    profile_id: int,
    start_date: date,
    end_date: date,
    standard_jar_or_cashback: str,
    selected_account_type: str,
) -> None:
    statement_csv = statement_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"Download {standard_jar_or_cashback} statement as CSV",
        data=statement_csv,
        file_name=f"Wise_{standard_jar_or_cashback}_statement-{profile_id}-EUR-{selected_account_type}-START-"
        f"{start_date.strftime('%d.%m.%Y')}-END-{end_date.strftime('%d.%m.%Y')}.csv",
        mime="text/csv",
    )
    excel_data = convert_dataframe_to_excel(statement_df)
    st.download_button(
        label=f"Download {standard_jar_or_cashback} statement as Excel",
        data=excel_data,
        file_name=f"Wise_{standard_jar_or_cashback}_statement-{profile_id}-EUR-{selected_account_type}-START-"
        f"{start_date.strftime('%d.%m.%Y')}-END-{end_date.strftime('%d.%m.%Y')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    st.title(f"{standard_jar_or_cashback} Account Statement")
    if standard_jar_or_cashback == "Cashback":
        st.write(
            "Cashback transactions from standard and jar accounts are both included."
        )
    st.write(statement_df)


def show_page_metadata(
    profile_data: dict,
    standard_balances: dict | list | None = None,
    jar_balances: dict | list | None = None,
) -> None:
    if not standard_balances:
        standard_balances = {}
    if not jar_balances:
        jar_balances = {}
    st.header("Profile metadata")
    st.json(profile_data)
    st.header("Standard account balances metadata")
    st.json(standard_balances)
    st.header("Jar account balances metadata")
    st.json(jar_balances)


if __name__ == "__main__":
    main()
