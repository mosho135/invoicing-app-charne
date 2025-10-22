import datetime as dt
import time
import pytz

import gspread
import numpy as np
import pandas as pd
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
from streamlit_option_menu import option_menu
from streamlit_autorefresh import st_autorefresh


south_africa_tz = pytz.timezone('Africa/Johannesburg')

@st.cache_resource
def get_gspread_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["google"], scope
    )
    client = gspread.authorize(creds)
    return client


@st.cache_data
def fetch_sheet_data(_sheet, name):
    worksheet = _sheet.get_all_records()
    df = pd.DataFrame(worksheet)
    return df


client = get_gspread_client()
invoice_workbook = client.open("invoices_app")
invoices = invoice_workbook.worksheet("cp_invoices")
customers = invoice_workbook.worksheet("cp_customers")
avonstock = invoice_workbook.worksheet("cp_avonstock")
detergentstock = invoice_workbook.worksheet("cp_detergentstock")
shopstock = invoice_workbook.worksheet("cp_shopstock")


class Production:
    def __init__(self):
        self.invoices = pd.DataFrame()
        self.customers = pd.DataFrame()
        self.avonstock = pd.DataFrame()
        self.detergentstock = pd.DataFrame()
        self.shopstock = pd.DataFrame()
        self.today = pd.to_datetime(dt.datetime.now(south_africa_tz).strftime("%Y/%m/%d %H:%M"))
        self.new_status = ""

    def format_data(self):
        df = fetch_sheet_data(invoices, 'invoices')
        df["OrderDate"] = pd.to_datetime(df["OrderDate"])
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
        df["PaymentDate"] = pd.to_datetime(df["PaymentDate"])
        self.invoices = df.copy()
        self.customers = fetch_sheet_data(customers, 'customers')
        self.avonstock = fetch_sheet_data(avonstock, 'avonstock')
        self.detergentstock = fetch_sheet_data(detergentstock, 'detergentstock')
        self.shopstock = fetch_sheet_data(shopstock, 'shopstock')

    def display_data(self):
        self.format_data()

        if st.button("Refresh Table"):
            st.cache_data.clear()
            st.rerun()

        def merge_data(customer_data, invoice_data, stock_data):
            df = customer_data.merge(invoice_data, on='CustomerID', how='left')
            df = df.merge(stock_data, on='StockNo', how='left')
            return df

        avon_data = merge_data(self.customers, self.invoices, self.avonstock)
        detergent_data = merge_data(self.customers, self.invoices, self.detergentstock)
        shop_data = merge_data(self.customers, self.invoices, self.shopstock)

        def sidebar_option_menu(m_options):
            m_icons = []
            for i in range(len(m_options)):
                m_icons.append("book")

            with st.sidebar:
                selected = option_menu(
                    menu_title="MAIN MENU",
                    options=m_options,
                    icons=m_icons,
                    menu_icon="cast",
                    orientation="vertical",
                )
            return selected

        side_options = ["Avon", "Detergents", "Koep en Loep"]
        sidebar_menu = sidebar_option_menu(side_options)

        if sidebar_menu == 'Avon':
            avon_navigation = st.radio(label="Navigation", options=["Current Invoices", "Add Invoice", "Add New Customer"], horizontal=True)
            
            if avon_navigation == "Current Invoices":
                AgGrid(self.customers, height=400, key="All_Customers")
            elif avon_navigation == "Add Invoice":
                st.write("In Progress")
            elif avon_navigation == "Add New Customer":
                self.add_customer()

        elif sidebar_menu == 'Detergents':
            st.write('Detergents]')
        elif sidebar_menu == 'Koep en Loep':
            st.write('Koep en Loep')

    def add_customer(self):
        # Add a new job
        st.subheader("Add New Customer")
        with st.form("customer_form", clear_on_submit=True):
            fr_col1, fr_col2 = st.columns(2)
            with fr_col1:
                customername = st.text_input("Firstname")
            with fr_col2:
                customersurname = st.text_input("Surname")

            sr_col1, sr_col2 = st.columns(2)
            with sr_col1:
                customercell = st.text_input("Cell Phone Number")
            with sr_col2:
                customeremail = st.text_input("Email Address")

            tr_col1, tr_col2 = st.columns(2)
            with tr_col1:
                address1 = st.text_input("Address1")
            with tr_col2:
                address2 = st.text_input("Address2")

            hr_col1, hr_col2 = st.columns(2)
            with hr_col1:
                address3 = st.text_input("Address3")
            with hr_col2:
                address4 = st.text_input("Address4")

            l_col1, l_col2 = st.columns(2)
            with l_col1:
                postalcode = st.text_input("Postal Code")

            customer_submit = st.form_submit_button("Add Customer")


            if customer_submit:
                self.format_data()
                j_list = self.customers["CustomerID"].unique().tolist()
                j_list.sort()
                wid = j_list[-1] + 1

                new_job = {
                    "CustomerID": [wid],
                    "CustomerName": [customername],
                    "CustomerSurname": [customersurname],
                    "CustomerCell": [customercell],
                    "CustomerEmail": [customeremail],
                    "Address1": [address1],
                    "Address2": [address2],
                    "Address3": [address3],
                    "Address4": [address4],
                    "PostalCode": [postalcode],
                }

                new_job_df = pd.DataFrame(new_job)
                self.customers = pd.concat([self.customers, new_job_df], ignore_index=True)
                self.customers = self.customers.astype(str)
                customers.update(
                    [self.customers.columns.values.tolist()] + self.customers.values.tolist()
                )
                # self.jobs_df.to_csv("foilwork_jobs.csv", index=False)
                st.success(f"Customer {wid} added!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()
