import datetime as dt
import time
import pytz
import io

import gspread
import numpy as np
import pandas as pd
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
from streamlit_option_menu import option_menu
from streamlit_autorefresh import st_autorefresh
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet


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
st.cache_data.clear()
invoice_workbook = client.open("invoices_app")
# invoice_workbook = client.open("test_invoices_app")
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
        df["InvoiceNo"] = pd.to_numeric(df["InvoiceNo"])
        df["CustomerID"] = pd.to_numeric(df["CustomerID"])
        df["StockNo"] = pd.to_numeric(df["StockNo"])
        self.invoices = df.copy()

        customer_df = fetch_sheet_data(customers, 'customers')
        customer_df["CustomerID"] = pd.to_numeric(customer_df["CustomerID"])
        customer_df["CustomerCell"] = pd.to_numeric(customer_df["CustomerCell"], errors="coerce")
        self.customers = customer_df.copy()

        avonstock_df = fetch_sheet_data(avonstock, 'avonstock')
        avonstock_df["StockNo"] = pd.to_numeric(avonstock_df["StockNo"])
        self.avonstock = avonstock_df.copy()

        detergentstock_df = fetch_sheet_data(detergentstock, 'detergentstock')
        detergentstock_df["StockNo"] = pd.to_numeric(detergentstock_df["StockNo"])
        self.detergentstock = detergentstock_df.copy()

        shopstock_df = fetch_sheet_data(shopstock, 'shopstock')
        shopstock_df["StockNo"] = pd.to_numeric(shopstock_df["StockNo"])
        self.shopstock = shopstock_df.copy()

    def display_data(self):
        self.format_data()

        if st.button("Refresh Table"):
            st.cache_data.clear()
            st.rerun()

        def merge_data(customer_data, invoice_data, stock_data, paid="N", invoice_type=1):
            df = customer_data.merge(invoice_data, on='CustomerID', how='inner')
            df = df.merge(stock_data, on='StockNo', how='inner')
            payment_df = df.loc[(df['Paid'] == paid) & (df['InvoiceType'] == invoice_type)].copy()
            sorted_df = payment_df.sort_values(by="InvoiceNo", ascending=True)
            display_df = sorted_df[['InvoiceNo', 'StockName', 'Quantity', 'UnitPrice', 'InvoiceTotal', 'CustomerName', 'CustomerSurname', 'CustomerCell', 'OrderDate', 'Paid', 'Id']].copy()
            return display_df

        not_paid_avon_data = merge_data(self.customers, self.invoices, self.avonstock, "N", 1)
        not_paid_detergent_data = merge_data(self.customers, self.invoices, self.detergentstock, "N", 2)
        not_paid_shop_data = merge_data(self.customers, self.invoices, self.shopstock, "N", 3)

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
            avon_navigation = st.radio(label="Navigation", options=["Current Invoices", "Add Invoice", "Customers", "Stock"], horizontal=True)

            if avon_navigation == "Current Invoices":
                self.update_job(display_df=not_paid_avon_data, status_update="Paid", store_name="Avon", aggrid_key="avon_data")
            elif avon_navigation == "Add Invoice":
                self.add_invoice(invoice_type_from_store='Avon', stock_type=self.avonstock)
            elif avon_navigation == "Customers":
                avon_customer_radio = st.radio(label="Customer Navigation", options=["All Customers", "Add New Customers"])
                if avon_customer_radio == "All Customers":
                    AgGrid(self.customers, height=400, key="avon_customer_data")
                else:
                    self.add_customer()
            elif avon_navigation == "Stock":
                avon_stock_radio = st.radio(label="Stock Navigation", options=["All Stock", "Add Stock"])
                if avon_stock_radio == "All Stock":
                    AgGrid(self.avonstock, height=400, key="avon_stock_data")
                else:
                    self.add_stock(stock_data=self.avonstock, sheet_to_update=avonstock)


        elif sidebar_menu == 'Detergents':
            detergent_navigation = st.radio(label="Navigation", options=["Current Invoices", "Add Invoice", "Customers", "Stock"], horizontal=True)

            if detergent_navigation == "Current Invoices":
                self.update_job(display_df=not_paid_detergent_data, status_update="Paid", store_name="Detergents", aggrid_key="detergent_data")
            elif detergent_navigation == "Add Invoice":
                self.add_invoice(invoice_type_from_store='Detergents', stock_type=self.detergentstock)
            elif detergent_navigation == "Customers":
                detergent_customer_radio = st.radio(label="Customer Navigation", options=["All Customers", "Add New Customers"])
                if detergent_customer_radio == "All Customers":
                    AgGrid(self.customers, height=400, key="detergent_customer_data")
                else:
                    self.add_customer()
            elif detergent_navigation == "Stock":
                detergent_stock_radio = st.radio(label="Customer Navigation", options=["All Stock", "Add Stock"])
                if detergent_stock_radio == "All Stock":
                    AgGrid(self.detergentstock, height=400, key="detergent_stock_data")
                else:
                    self.add_stock(stock_data=self.detergentstock, sheet_to_update=detergentstock)


        elif sidebar_menu == 'Koep en Loep':
            st.write('Koep en Loep')

    def add_stock(self, stock_data, sheet_to_update):
        st.subheader("Add New Stock")
        with st.form("stock_form", clear_on_submit=True):
            fr_col1, fr_col2 = st.columns(2)
            with fr_col1:
                stockname = st.text_input("Stock Name")

            stock_submit = st.form_submit_button("Add Stock")

            stock_list = stock_data['StockName'].unique().tolist()

            if stock_submit:
                if stockname.strip() not in stock_list:
                    self.format_data()
                    j_list = stock_data["StockNo"].unique().tolist()
                    j_list.sort()
                    wid = int(j_list[-1]) + 1

                    new_job = {
                        "StockNo": [wid],
                        "StockName": [stockname],
                    }

                    new_job_df = pd.DataFrame(new_job)
                    stock_data = pd.concat([stock_data, new_job_df], ignore_index=True)
                    stock_data = stock_data.astype(str)
                    sheet_to_update.update(
                        [stock_data.columns.values.tolist()] + stock_data.values.tolist()
                    )
                    st.success(f"Stock item {wid} added!")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Stock Item already exists")


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

    def add_invoice(self, invoice_type_from_store=None, stock_type=None):
        st.subheader("Add New Invoice")

        invoice_type_dict = {
            'Avon': 1,
            'Detergents': 2,
            'Koep en Loep': 3
        }

        def create_number_of_items(total_items, stock_data_list):
            item_list = {}
            for _ in range(int(total_items)):
                tr_col1, tr_col2, tr_col3 = st.columns(3)

                with tr_col1:
                    item_selected = st.selectbox(label="Exisiting Item Ordered", options=stock_data_list, key=f"existing_item_{_}")
                with tr_col2:
                    item_qty = st.number_input("Quantity", min_value=1, step=1, key=f"item_qty_{_}")
                with tr_col3:
                    item_value = st.number_input("Price", key=f"price{_}")

                item_list[item_selected] = [item_qty, item_value]
                st.divider()

            return item_list


        # Create Customer List
        customer_temp = self.customers.copy()
        customer_temp['FullName'] = customer_temp['CustomerName'] + ' ' + customer_temp['CustomerSurname']
        customer_list = customer_temp['FullName'].unique().tolist()
        customer_list.sort()


        stock_data_list = stock_type['StockName'].unique().tolist()
        stock_data_list.sort()


        with st.container(border=True):
            fr_col1, fr_col2 = st.columns(2)
            with fr_col1:
                customerfullname = st.selectbox(label='Customer', options=customer_list, key="customer")

            sr_col1, sr_col2 = st.columns(2)
            with sr_col1:
                if st.session_state.get("reset_invoice_form", False):
                    for key in list(st.session_state.keys()):
                        if key.startswith(("item_type", "new_item_", "existing_item_", "item_qty_", "price", "total_items_ordered")):
                            del st.session_state[key]
                    st.session_state["reset_invoice_form"] = False
                total_items_ordered = st.number_input("Total Items", min_value=0, step=1, key="total_items_ordered")

            if total_items_ordered > 0:

                all_items_ordered = create_number_of_items(total_items=total_items_ordered, stock_data_list=stock_data_list)


                if st.button("Add Invoice"):
                    self.format_data()
                    j_list = self.invoices["InvoiceNo"].unique().tolist()
                    j_list.sort()
                    wid = j_list[-1] + 1

                    customerid_selection = customer_temp.loc[customer_temp["FullName"] == customerfullname, "CustomerID"].sum()
                    invoice_type = invoice_type_dict[invoice_type_from_store]

                    for item in all_items_ordered.items():
                        i_list = self.invoices["Id"].unique().tolist()
                        i_list.sort()
                        iid = int(i_list[-1]) + 1
                        stocknoselection = stock_type.loc[stock_type["StockName"] == item[0], "StockNo"].sum()
                        itemqty = item[1][0]
                        unitprice = item[1][1]
                        invoicetotal = unitprice * itemqty
                        new_job = {
                            "InvoiceNo": [wid],
                            "CustomerID": [customerid_selection],
                            "StockNo": [stocknoselection],
                            "OrderDate": [self.today],
                            "InvoiceType": [invoice_type],
                            "Quantity": [itemqty],
                            "UnitPrice": [unitprice],
                            "InvoiceTotal": [invoicetotal],
                            "Paid": ["N"],
                            "Id": [iid],
                        }

                        new_job_df = pd.DataFrame(new_job)
                        self.invoices = pd.concat([self.invoices, new_job_df], ignore_index=True)
                        self.invoices = self.invoices.astype(str)
                        invoices.update(
                            [self.invoices.columns.values.tolist()] + self.invoices.values.tolist()
                        )

                    st.success(f"Invoice {wid} added!")
                    st.session_state["reset_invoice_form"] = True

                    # Optional: clear related session states if you want to fully reset inputs
                    for key in list(st.session_state.keys()):
                        if key.startswith(("item_type", "new_item_", "existing_item_", "item_qty_", "price")):
                            del st.session_state[key]
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()

    def update_job(self, display_df, status_update, store_name ,aggrid_key):

        # Create grid options
        gb = GridOptionsBuilder.from_dataframe(display_df)
        gb.configure_selection(
            "multiple", use_checkbox=True
        )  # Enable single row selection

        grid_options = gb.build()

        # Display the grid
        grid_response = AgGrid(
            display_df,
            gridOptions=grid_options,
            allow_unsafe_jscode=True,
            enable_enterprise=False,
            height=400,
            key=aggrid_key,
        )

        # Get selected row data
        selected_rows = pd.DataFrame(grid_response.get("selected_rows", []))
        # st.write(selected_rows)

        # Ensure selected_rows is not empty
        if not selected_rows.empty:  # Check if there's at least one selected row
            task_id = selected_rows["Id"].tolist()

            # Create a form to edit the status
            new_status = status_update

            btn_col1, btn_col2, btn_col3, btn_col4 = st.columns([0.5, 0.5, 0.5, 1])
            with btn_col1:
                submit_button = st.button("Paid Invoice")

            # Fix the below error
            if submit_button:
                for j_id in task_id:
                    if new_status == "Paid":
                        self.invoices["Paid"] = np.where(self.invoices["Id"] == j_id, "Y", self.invoices["Paid"],)
                        self.invoices.loc[self.invoices["Id"] == j_id, "PaymentDate"] = {self.today}

                        self.invoices = self.invoices.astype(str)
                        invoices.update(
                            [self.invoices.columns.values.tolist()]
                            + self.invoices.values.tolist()
                        )
                st.success("Job has been updated")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

            with btn_col2:
                delete_button = st.button("Delete Invoice")
            if delete_button:
                for i_id in task_id:
                    jobs_to_delete = self.invoices.loc[
                        self.invoices["Id"] == i_id
                    ].index

                    # Adjust index for Google Sheets (1-based indexing)
                    rows_to_delete = [
                        index + 2 for index in jobs_to_delete
                    ]  # +2 to skip the header row

                    # Delete rows in reverse order to avoid shifting issues
                    for row in sorted(rows_to_delete, reverse=True):
                        invoices.delete_rows(row)

                st.success("Invoice has been deleted")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

            with btn_col3:
                payment_date_selection = st.date_input(label="Payment Date", min_value=self.today, label_visibility="collapsed")

            with btn_col4:
                if st.button("Generate Invoice"):
                    selected_rows['FullName'] = selected_rows['CustomerName'] + ' ' + selected_rows['CustomerSurname']
                    df = selected_rows.drop_duplicates('FullName')
                    filename = df['FullName'].sum() + '_' + store_name + '_' + str(df['InvoiceNo'].sum()) + "_" + dt.datetime.now().strftime("%d%m%Y%H%M%S") + ".pdf"

                    pdf_bytes = self.print_invoice(invoice_data=selected_rows, store_name=store_name, payment_date=payment_date_selection)

                    st.download_button(
                        label="Download Invoice",
                        data=pdf_bytes,
                        file_name=filename,
                        mime="application/pdf",
                    )

    def print_invoice(self, invoice_data, store_name, payment_date):
        # === PDF Setup ===
        buffer = io.BytesIO()
        invoice_data['FullName'] = invoice_data['CustomerName'] + ' ' + invoice_data['CustomerSurname']
        df = invoice_data.drop_duplicates('FullName')
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=25,
            leftMargin=25,
            topMargin=40,
            bottomMargin=25,
        )
        styles = getSampleStyleSheet()
        elements = []

        # === HEADER ===
        # Optional: Add a company logo
        # If you have a logo file, uncomment this line and set the path
        # elements.append(Image("logo.png", width=80, height=40))
        # elements.append(Spacer(1, 12))

        elements.append(Paragraph(f"<b>{store_name.upper()} INVOICE</b>", styles["Title"]))
        elements.append(Spacer(1, 12))

        company_info = f"""
        <b>Charne's {store_name}</b><br/>
        charneypangle0@igmail.com | 079 211 2694 / 060 681 2836
        """
        elements.append(Paragraph(company_info, styles["Normal"]))
        elements.append(Spacer(1, 12))

        # === INVOICE DETAILS ===
        invoice_meta = f"""
        <b>Invoice Number:</b> {str(df['InvoiceNo'].sum())}<br/>
        <b>Date:</b> {dt.datetime.now().strftime('%d %B %Y')}<br/>
        <b>Customer:</b> {df['FullName'].sum()}<br/>
        """
        elements.append(Paragraph(invoice_meta, styles["Normal"]))
        elements.append(Spacer(1, 16))

        # === TABLE DATA ===
        table_data = [["Item", "Qty", "Unit Price", "Total"]]
        for _, row in invoice_data.iterrows():
            table_data.append([
                row["StockName"],
                row["Quantity"],
                f"R {row['UnitPrice']:.2f}",
                f"R {row['InvoiceTotal']:.2f}",
            ])

        total_amount = invoice_data["InvoiceTotal"].sum()
        table_data.append(["", "", "Total", f"R {total_amount:.2f}"])

        # === TABLE STYLING ===
        page_width, _ = A4
        left_margin = 25
        right_margin = 25
        usable_width = page_width - left_margin - right_margin

        col_widths = [usable_width * 0.55, usable_width * 0.10, usable_width * 0.15, usable_width * 0.20]
        table = Table(table_data, colWidths=col_widths, hAlign='LEFT')
        table.setStyle(
            TableStyle(
                [
                    # Header
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    # Body
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -2), 10),
                    ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    # Alternate row background
                    ("BACKGROUND", (0, 1), (-1, -2), colors.whitesmoke),
                    # Total row
                    ("FONTNAME", (-2, -1), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (-2, -1), (-1, -1), 11),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
                    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8e8e8")),
                    ("ALIGN", (0, -1), (-1, -1), "CENTER"),
                ]
            )
        )

        elements.append(table)
        elements.append(Spacer(1, 24))

        # === FOOTER ===
        elements.append(
                Paragraph(f"<i>Payment is due {payment_date.strftime('%d %B %Y')}</i>", styles["Italic"])
        )

        # === BUILD PDF ===
        pdf.build(elements)
        buffer.seek(0)
        return buffer.read()
