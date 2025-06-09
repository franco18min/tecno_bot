from flask import Flask, request, jsonify
import requests
import json
import psycopg2
import sys
import urllib.parse
import traceback
import datetime
import re
import unicodedata

app = Flask(__name__)

# Credenciales
VERIFY_TOKEN = "franco"
PHONE_NUMBER_ID = "673684182490001"
ACCESS_TOKEN = "EAAJekovvYhwBO8i0AtsPKi3Tnn8NpmdZA1cUrIXkJamefHXZBSyljhu2OW2uXdJAPDHAbZB5piZCPwCs9MI0iL31JmB8euQxFTrSZAKDScNKTmVn70qHs9ZArFQ5lDbTjaNoYxpX2LGuPjpKYFSW2ZA4EUtVZAyFwcFUXlll1lB9yf8c8s6tfeecieguoh5R8ETCZBDdkRVpqJ1UTmAe65aNFJidets5KPUIFrNEZD01                                                                                                                                 "

DB_HOST = "localhost"
DB_NAME = "tecno_bot"
DB_USER = "postgres"
DB_PASSWORD = "franco"
DB_PORT = "5432"

SALESPERSON_PHONE_NUMBER = "5493884440133"
BASE_PRODUCT_URL = "https://tecnomundo.ar/producto/"

token_is_invalid = False
user_states = {}

STATE_INITIAL = "initial"
STATE_AWAITING_NEXT_ACTION = "awaiting_next_action"
STATE_AWAITING_CATEGORY_CHOICE = "awaiting_category_choice"
STATE_AWAITING_SUBCATEGORY_CHOICE = "awaiting_subcategory_choice"
STATE_AWAITING_PRODUCT_CHOICE = "awaiting_product_choice"
STATE_AWAITING_POST_PRODUCT_ACTION = "awaiting_post_product_action"
STATE_ASKING_ORDER_NUMBER_FOR_COORDINATION = "asking_order_number_for_coordination"
STATE_AWAITING_PAYMENT_METHOD = "awaiting_payment_method"
STATE_AWAITING_DELIVERY_CHOICE = "awaiting_delivery_choice"
STATE_AWAITING_SHIPPING_ADDRESS = "awaiting_shipping_address"
STATE_AWAITING_PROBLEM_DESCRIPTION = "awaiting_problem_description"

NAV_ID_MAIN_MENU = "_nav_main_menu_"
NAV_ID_BACK_TO_CATEGORIES = "_nav_back_to_categories_"
NAV_ID_BACK_TO_SUBCATEGORIES = "_nav_back_to_subcategories_"
NAV_ID_NEXT_PAGE = "_nav_next_page_"
NAV_ID_PREVIOUS_PAGE = "_nav_prev_page_"

PAYMENT_ID_CASH = "_pay_cash_"
PAYMENT_ID_TRANSFER = "_pay_transfer_"
DELIVERY_ID_SHIP = "_del_ship_"
DELIVERY_ID_PICKUP = "_del_pickup_"
POST_PRODUCT_CONTACT_SALES = "_post_prod_contact_sales_"
POST_PRODUCT_SEARCH_AGAIN = "_post_prod_search_again_"

PRODUCTS_PER_PAGE = 6  # MODIFICADO

MAIN_MENU_MESSAGE = """👋 ¡Hola! Soy TecnoBot, tu asistente virtual de TecnoMundo. ¡Gracias por comunicarte! 😊

Estoy aquí para ayudarte con tus consultas. Por favor, elige una opción del menú:

1️⃣  Coordinar envío/retiro y forma de pago (con N° de pedido) 🚚💰
    *(Para esta opción, necesitarás tu número de orden de pedido. Lo encuentras en el email de confirmación de tu compra).*
2️⃣  Ver stock de productos 🛍️
3️⃣  Ayuda con un problema o reclamo 🛠️
4️⃣  Hablar con un vendedor 🙋‍♂️

📌 Responde con el número de la opción que necesitas."""


def normalize_text(text):
    if not text: return ""
    text = text.lower();
    nfkd_form = unicodedata.normalize('NFKD', text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


def generate_product_slug(product_name, product_code=None):
    if not product_name: return ""
    slug = str(product_name).lower()
    slug = slug.replace(' + ', '__')
    slug = slug.replace('+', '-')
    slug = slug.replace('–', '-')
    slug = slug.replace('—', '-')
    slug = slug.replace('/', '-')
    slug = re.sub(r'(\d)\.(\d[mM]?)', r'\1-\2', slug)
    slug = re.sub(r'(\d)\.(\d)(?![.\d]*[mM])', r'\1-\2', slug)
    replacements = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u', 'ñ': 'n', 'ä': 'a', 'ë': 'e', 'ï': 'i',
                    'ö': 'o'}
    for acc, unacc in replacements.items(): slug = slug.replace(acc, unacc)
    slug = re.sub(r'[^a-z0-9_-]', ' ', slug)
    slug = re.sub(r'\s+', '_', slug)
    if '__' in slug:
        slug = slug.replace('__', '_TEMPSEP_')
        slug = re.sub(r'_+', '_', slug)
        slug = slug.replace('_TEMPSEP_', '__')
    else:
        slug = re.sub(r'_+', '_', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('_-')
    return slug[:150]


def get_distinct_categories_from_db():
    conn = None;
    cur = None;
    categories_data = []
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD, port=DB_PORT)
        cur = conn.cursor();
        sql_query = 'SELECT "id_categoria", TRIM("nombre") as nombre_categoria FROM categorias ORDER BY nombre_categoria;'
        cur.execute(sql_query);
        rows = cur.fetchall()
        if rows:
            for row in rows: categories_data.append({'id': row[0], 'name': row[1]})
    except Exception as e:
        print(f"Error get_distinct_categories_from_db: {e}"); traceback.print_exc()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return categories_data


def get_subcategories_from_db(category_id):
    conn = None;
    cur = None;
    subcategories_data = []
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD, port=DB_PORT)
        cur = conn.cursor();
        sql_query = 'SELECT "id_subcategoria", TRIM("nombre") as nombre_subcategoria FROM subcategorias WHERE "id_categoria" = %s ORDER BY nombre_subcategoria;'
        cur.execute(sql_query, (category_id,));
        rows = cur.fetchall()
        if rows:
            for row in rows: subcategories_data.append({'id': row[0], 'name': row[1]})
    except Exception as e:
        print(f"Error get_subcategories_from_db para category_id {category_id}: {e}"); traceback.print_exc()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return subcategories_data


def get_products_from_db(category_id, subcategory_id=None):
    conn = None;
    cur = None;
    products_list = []
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD, port=DB_PORT)
        cur = conn.cursor()
        select_columns = '"Codigo", "Nombre", "url_producto"'
        if subcategory_id is not None:
            sql_query = f'SELECT {select_columns} FROM productos WHERE "id_categoria" = %s AND "id_subcategoria" = %s ORDER BY "Nombre";'
            params = (category_id, subcategory_id)
        else:
            sql_query = f'SELECT {select_columns} FROM productos WHERE "id_categoria" = %s AND "id_subcategoria" IS NULL ORDER BY "Nombre";'
            params = (category_id,)
        cur.execute(sql_query, params);
        rows = cur.fetchall()
        if rows:
            for row in rows: products_list.append({'code': row[0], 'name': row[1], 'page_url': row[2]})
    except psycopg2.Error as e:
        print(f"Error de base de datos en get_products_from_db: {e}");
        query_string = "No query disponible"
        if cur and cur.query:
            try:
                query_string = cur.query.decode('utf-8') if isinstance(cur.query, bytes) else str(cur.query)
            except Exception:
                query_string = str(cur.query)
        print(f"SQL Query: {query_string}");
        traceback.print_exc()
    except Exception as e:
        print(f"Error general en get_products_from_db: {e}"); traceback.print_exc()
    finally:
        if cur: cur.close()
        if conn: conn.close()
    return products_list


def send_message(to, text_body):
    global token_is_invalid
    if token_is_invalid: print(f"send_message BLOQUEADO."); return {"status": "error"}
    url_api = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages";
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    text_object = {"body": text_body}
    if "http://" in text_body or "https://" in text_body: text_object["preview_url"] = True
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": text_object}
    print(f"Enviando TEXTO a {to}: '{text_body[:70]}...'. Payload: {json.dumps(data, indent=2)}")
    try:
        response = requests.post(url_api, headers=headers, data=json.dumps(data));
        response_data = response.json()
        print(f"Respuesta API (texto) para {to}: STATUS={response.status_code} - BODY='{response_data}'")
        if response.status_code == 401: token_is_invalid = True; print("TOKEN INVÁLIDO!"); sys.exit("Token inválido.")
        return response_data
    except Exception as e:
        print(f"Excepción send_message: {e}"); return {"status": "error"}


def send_image_message(to, image_url, caption=None):
    global token_is_invalid
    if token_is_invalid: print(f"send_image BLOQUEADO."); return {"status": "error", "message": "Token inválido."}
    if not image_url or not image_url.startswith("http"): print(
        f"ADVERTENCIA: URL de imagen inválida: {image_url}"); return {"status": "error",
                                                                      "message": "URL de imagen inválida."}
    url_api = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "image", "image": {"link": image_url}}
    if caption and isinstance(caption, str) and caption.strip(): payload["image"]["caption"] = caption[:1024]
    print(f"DEBUG: Enviando IMAGEN a {to}. URL: {image_url}. Payload: {json.dumps(payload)}")
    try:
        response = requests.post(url_api, headers=headers, data=json.dumps(payload));
        response_data = response.json()
        print(f"Respuesta API (imagen) para {to}: STATUS={response.status_code} - BODY='{response.text}'")
        if response.status_code == 401: token_is_invalid = True; print("TOKEN INVÁLIDO!"); sys.exit("Token inválido.")
        return response_data
    except requests.exceptions.RequestException as e:
        print(f"Excepción send_image_message HTTP a {to}: {e}"); return {"status": "error", "message": str(e)}


def send_interactive_list_message(to, header_text, body_text, button_text, sections_data):
    global token_is_invalid
    if token_is_invalid: print(f"send_list BLOQUEADO."); return {"status": "error"}
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages";
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    header_text, body_text, button_text = header_text[:60], body_text[:1024], button_text[:20]
    for section in sections_data:
        section['title'] = section['title'][:24]
        for row in section.get('rows', []):
            row['title'] = str(row['title'])[:24]
            row['id'] = str(row['id'])[:200]
            if 'description' in row and row['description']:
                row['description'] = str(row['description'])[:72]
            elif 'description' in row and row['description'] is None:
                del row['description']
    payload = {"type": "list", "header": {"type": "text", "text": header_text}, "body": {"text": body_text},
               "action": {"button": button_text, "sections": sections_data}}
    data = {"messaging_product": "whatsapp", "to": to, "type": "interactive", "interactive": payload};
    print(f"DEBUG: Enviando LISTA a {to}. Header: '{header_text}'. Payload completo: {json.dumps(payload, indent=2)}")
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data));
        response_data = response.json();
        print(f"Respuesta API (lista) para {to}: STATUS={response.status_code} - BODY='{response.text}'")
        if response.status_code == 401: token_is_invalid = True; print("TOKEN INVÁLIDO!"); sys.exit("Token inválido.")
        if 'error' in response_data and response_data['error'].get('code') == 131031: send_message(to,
                                                                                                   f"{header_text}\n{body_text}\n(Opción por texto)"); return {
            "status": "fallback"}
        return response_data
    except Exception as e:
        print(f"Excepción send_list: {e}"); return {"status": "error"}


def send_interactive_buttons_message(to, body_text, buttons_data):
    global token_is_invalid
    if token_is_invalid: print(f"send_buttons BLOQUEADO."); return {"status": "error"}
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages";
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    if len(buttons_data) > 3: buttons_data = buttons_data[:3]
    action_buttons = [{"type": "reply", "reply": {"id": btn['id'][:256], "title": btn['title'][:20]}} for btn in
                      buttons_data]
    payload = {"type": "button", "body": {"text": body_text[:1024]}, "action": {"buttons": action_buttons}}
    data = {"messaging_product": "whatsapp", "to": to, "type": "interactive", "interactive": payload};
    print(
        f"DEBUG: Enviando BOTONES a {to}. Body: '{body_text[:50]}...'. Payload completo: {json.dumps(payload, indent=2)}")
    try:
        response = requests.post(url, headers=headers, data=json.dumps(data));
        response_data = response.json();
        print(f"Respuesta API (botones) para {to}: STATUS={response.status_code} - BODY='{response.text}'")
        if response.status_code == 401: token_is_invalid = True; print("TOKEN INVÁLIDO!"); sys.exit("Token inválido.")
        if 'error' in response_data and response_data['error'].get('code') == 131031: send_message(to,
                                                                                                   f"{body_text}\n(Opción por texto)"); return {
            "status": "fallback"}
        return response_data
    except Exception as e:
        print(f"Excepción send_buttons: {e}"); return {"status": "error"}


def create_list_rows_with_map(items_data, is_product_list=False, max_title_length=24, max_desc_length=72):
    rows = [];
    whatsapp_row_id_to_item_id_map = {};
    temp_id_generator_set = set()
    for item in items_data:
        item_id_value = item['id'];
        display_name = item['name']
        if not display_name: print(
            f"ADVERTENCIA en create_list_rows: item sin display_name. ID: {item_id_value}"); continue
        row_data = {"id": ""}
        if str(item_id_value).startswith(("_nav_", "_pay_", "_del_", "_post_prod_")):
            whatsapp_row_id = str(item_id_value); row_data["title"] = str(display_name)[:max_title_length]
        else:
            base_id = str(display_name).lower().replace('/', '_slash_')
            base_id = ''.join(c for c in base_id if c.isalnum() or c == ' ' or c == '_slash_').replace(" ",
                                                                                                       "_").replace(
                "_slash_", "-")
            base_id = ''.join(c for c in base_id if c.isalnum() or c in ['-', '_'])[:180];
            whatsapp_row_id = base_id
            if not whatsapp_row_id:
                print(
                    f"ADVERTENCIA: ID de fila sanitizado vacío para '{display_name}'. Usando ID numérico si es posible o saltando.")
                if isinstance(item_id_value, int):
                    whatsapp_row_id = f"item_{item_id_value}"
                elif isinstance(item_id_value, str) and item_id_value.isalnum():
                    whatsapp_row_id = f"item_{item_id_value}"
                else:
                    print(
                        f"SALTANDO item '{display_name}' porque no se pudo generar ID de fila válido (ID original: {item_id_value}).")
                    continue
            s_count = 0
            temp_final_id = whatsapp_row_id
            while temp_final_id in temp_id_generator_set: s_count += 1; temp_final_id = f"{whatsapp_row_id}_{s_count}"[
                                                                                        :200]
            whatsapp_row_id = temp_final_id
            if is_product_list:
                row_data["title"] = str(display_name)[:max_title_length]
                if len(str(display_name)) > max_title_length: row_data["description"] = str(display_name)[
                                                                                        max_title_length:max_title_length + max_desc_length]
            else:
                row_data["title"] = str(display_name)[:max_title_length]
        temp_id_generator_set.add(whatsapp_row_id);
        row_data["id"] = whatsapp_row_id;
        rows.append(row_data)
        whatsapp_row_id_to_item_id_map[whatsapp_row_id] = item_id_value
    return rows, whatsapp_row_id_to_item_id_map


def display_categories_list(sender):
    print(f"DEBUG: display_categories_list (siempre lista) para {sender}")
    send_message(sender, "¡Perfecto! Busquemos ese producto. 🔎")
    categories_data = get_distinct_categories_from_db()
    if not categories_data:
        print(f"DEBUG: No hay categorías en DB para {sender}.")
        send_message(sender, "Ups, no hay categorías. 😔 Contacta a un vendedor.");
        user_states[sender] = {'state': STATE_AWAITING_NEXT_ACTION};
        return
    print(f"DEBUG: {len(categories_data)} categorías encontradas para lista para {sender}.")
    list_items = categories_data.copy()
    list_items.append({'id': NAV_ID_MAIN_MENU, 'name': '🏠 Menú Principal'})
    rows, category_map = create_list_rows_with_map(list_items)
    if not rows:
        print(f"DEBUG: No se generaron filas para lista cat para {sender}. Items: {list_items}");
        send_message(sender, "¡Vaya! No pude armar la lista. 🤔");
        user_states[sender] = {'state': STATE_AWAITING_NEXT_ACTION};
        return
    user_states[sender]['category_id_map'] = category_map
    print(f"DEBUG: category_id_map (lista) para {sender}: {user_states[sender]['category_id_map']}")
    sections = [{"title": "Nuestras Categorías ✨", "rows": rows}]
    response = send_interactive_list_message(sender, "Explora Categorías 🧭",
                                             "¿Qué tipo de producto buscas? Elige de la lista:", "Ver Opciones",
                                             sections)
    if response and response.get('messages') and response['messages'][0].get('id'):
        print(f"DEBUG: Lista de categorías ENVIADA con éxito a {sender}. msg_id: {response['messages'][0]['id']}")
        user_states[sender]['state'] = STATE_AWAITING_CATEGORY_CHOICE
    else:
        print(f"DEBUG: Fallo envío lista cat a {sender}. Resp API: {response}")
        send_message(sender, "Problema al mostrar categorías. 😬");
        user_states[sender]['state'] = STATE_AWAITING_NEXT_ACTION


def display_subcategories_list(sender, category_db_id, category_display_name):
    print(
        f"DEBUG: ***** INICIO display_subcategories_list para cat_id {category_db_id} ('{category_display_name}') *****")
    send_message(sender, f"¡Genial! Dentro de *{category_display_name}*, tenemos esto 👇")
    subcategories_data = get_subcategories_from_db(category_db_id)
    print(
        f"DEBUG: {len(subcategories_data)} subcategorías encontradas para '{category_display_name}': {subcategories_data}")
    if not subcategories_data:
        print(
            f"DEBUG: No hay subcategorías en DB para '{category_display_name}'. Mostrando productos directamente (subcategory_id=None).");
        user_states[sender]['selected_subcategory_id'] = None
        user_states[sender]['selected_subcategory_name'] = "General (sin subcategoría)"
        display_products_list(sender, category_db_id, category_display_name, None,
                              user_states[sender]['selected_subcategory_name'], page_offset=0)  # Iniciar paginación
        print(
            f"DEBUG: ***** FIN display_subcategories_list (ruta: no subcats). Estado: {user_states[sender].get('state')} *****")
        return
    is_single_sin_sub_categoria = False
    if len(subcategories_data) == 1:
        print(
            f"DEBUG: Única subcategoría encontrada: ID={subcategories_data[0]['id']}, Nombre='{subcategories_data[0]['name']}'")
        if subcategories_data[0]['name'].strip().upper() == "SIN SUB CATEGORIA":
            is_single_sin_sub_categoria = True
    if is_single_sin_sub_categoria:
        print(
            f"DEBUG: Única subcategoría es 'SIN SUB CATEGORIA' para '{category_display_name}'. Llamando a display_products_list.")
        sub_id = subcategories_data[0]['id']
        sub_name = subcategories_data[0]['name']
        user_states[sender]['selected_subcategory_id'] = sub_id
        user_states[sender]['selected_subcategory_name'] = sub_name
        display_products_list(sender, category_db_id, category_display_name, sub_id, sub_name,
                              page_offset=0)  # Iniciar paginación
        print(
            f"DEBUG: ***** FIN display_subcategories_list (ruta: SIN SUB CATEGORIA). Estado: {user_states[sender].get('state')} *****")
        return
    print(
        f"DEBUG: Múltiples subcategorías o una diferente de 'SIN SUB'. Preparando lista para '{category_display_name}'.")
    items_for_list = subcategories_data.copy()
    items_for_list.append({'id': NAV_ID_MAIN_MENU, 'name': '🏠 Menú Principal'})
    print(f"DEBUG: items_for_list (subcat) para '{category_display_name}': {items_for_list}")
    rows, subcategory_map = create_list_rows_with_map(items_for_list)
    if not rows:
        print(
            f"DEBUG: No se generaron filas para lista subcat para '{category_display_name}'. Items: {items_for_list}");
        send_message(sender, "¡Vaya! No pude armar la lista de subcategorías. 🤔");
        user_states[sender]['state'] = STATE_AWAITING_CATEGORY_CHOICE;
        print(
            f"DEBUG: ***** FIN display_subcategories_list (ruta: no rows). Estado: {user_states[sender].get('state')} *****")
        return
    user_states[sender]['subcategory_id_map'] = subcategory_map
    print(
        f"DEBUG: subcategory_id_map (lista) para '{category_display_name}': {user_states[sender]['subcategory_id_map']}")
    header = f"{category_display_name[:25]}";
    body = f"Elige una opción para *{category_display_name[:30]}*:"
    sections = [{"title": "Elige una Opción 👇", "rows": rows}]
    print(f"DEBUG: Intentando enviar lista de subcategorías para '{category_display_name}'...")
    response = send_interactive_list_message(sender, header, body, "Ver Opciones", sections)
    if response and response.get('messages') and response['messages'][0].get('id'):
        print(
            f"DEBUG: Lista de subcategorías ENVIADA con éxito para '{category_display_name}'. msg_id: {response['messages'][0]['id']}")
        user_states[sender]['state'] = STATE_AWAITING_SUBCATEGORY_CHOICE
    else:
        print(f"DEBUG: Fallo envío lista subcat para '{category_display_name}'. Resp API: {response}");
        send_message(sender, "¡Uy! Problema al mostrar subcategorías. 😥 ¿Volvemos a las categorías?");
        user_states[sender]['state'] = STATE_AWAITING_CATEGORY_CHOICE
    print(f"DEBUG: ***** FIN display_subcategories_list. Nuevo estado: {user_states[sender].get('state')} *****")


# MODIFICADA: display_products_list con paginación
def display_products_list(sender, category_db_id, category_display_name, subcategory_db_id,
                          subcategory_display_name_from_selection, page_offset=0):
    print(
        f"DEBUG: ***** INICIO display_products_list para Cat: '{category_display_name}', SubCat DB ID: {subcategory_db_id}, SubCat Display: '{subcategory_display_name_from_selection}', Offset: {page_offset} *****")

    effective_display_group_name = category_display_name
    is_direct_from_category_no_subcat = False
    if subcategory_db_id is not None:
        if subcategory_display_name_from_selection and \
                subcategory_display_name_from_selection.strip().upper() not in ["GENERAL (SIN SUBCATEGORÍA)",
                                                                                "SIN SUB CATEGORIA"]:
            effective_display_group_name = subcategory_display_name_from_selection
    else:
        is_direct_from_category_no_subcat = True

    print(f"DEBUG: Effective display group name: '{effective_display_group_name}'")
    if page_offset == 0:
        send_message(sender, f"¡Buscando en *{effective_display_group_name}*! ⏳ Un momento...")

    # Obtener y guardar todos los productos solo si es la primera página o si no están guardados/son de otra selección
    if page_offset == 0 or 'all_products_for_current_selection' not in user_states[sender] or \
            user_states[sender].get('current_selection_id_for_products') != (category_db_id, subcategory_db_id):
        all_products = get_products_from_db(category_db_id, subcategory_db_id)
        user_states[sender]['all_products_for_current_selection'] = all_products
        user_states[sender]['current_selection_id_for_products'] = (category_db_id, subcategory_db_id)
        user_states[sender]['current_products_details'] = {
            prod['code']: {'name': prod['name'], 'page_url': prod.get('page_url')}
            for prod in all_products
        }

    all_products_for_current_selection = user_states[sender].get('all_products_for_current_selection', [])
    total_products = len(all_products_for_current_selection)
    print(
        f"DEBUG: Productos totales para {category_display_name}>{subcategory_display_name_from_selection} (DB ID {subcategory_db_id}): {total_products}")

    if not all_products_for_current_selection:
        msg = f"¡Oh! No hay productos ahora en '{effective_display_group_name}'. 🙁"
        send_message(sender, msg)
        nav_options = []
        if not is_direct_from_category_no_subcat and subcategory_db_id is not None and \
                subcategory_display_name_from_selection.strip().upper() not in ["GENERAL (SIN SUBCATEGORÍA)",
                                                                                "SIN SUB CATEGORIA"]:
            nav_options.append({'id': NAV_ID_BACK_TO_SUBCATEGORIES, 'name': '↩️ Ver Subcategorías'})
        else:
            nav_options.append({'id': NAV_ID_BACK_TO_CATEGORIES, 'name': '↩️ Ver Categorías'})
        nav_options.append({'id': NAV_ID_MAIN_MENU, 'name': '🏠 Menú Principal'})
        rows, nav_map = create_list_rows_with_map(nav_options)
        if not rows:
            send_message(sender, "Parece que no hay opciones aquí. Volviendo al menú principal.");
            user_states[sender]['state'] = STATE_AWAITING_NEXT_ACTION
            print(
                f"DEBUG: ***** FIN display_products_list (no productos, no rows nav). Estado: {user_states[sender].get('state')} *****")
            return
        user_states[sender]['product_code_map'] = nav_map
        sections = [{"title": "¿Qué Hacemos? 🤔", "rows": rows}]
        response_nav = send_interactive_list_message(sender, "No Encontrados", "¿Qué deseas hacer a continuación?",
                                                     "Ver Opciones", sections)
        if response_nav and response_nav.get('messages') and response_nav['messages'][0].get('id'):
            user_states[sender]['state'] = STATE_AWAITING_PRODUCT_CHOICE
        else:
            send_message(sender, "Problema al mostrar opciones. Volviendo al menú.");
            user_states[sender]['state'] = STATE_AWAITING_NEXT_ACTION
        print(
            f"DEBUG: ***** FIN display_products_list (no productos). Estado: {user_states[sender].get('state')} *****")
        return

    start_index = page_offset
    end_index = page_offset + PRODUCTS_PER_PAGE
    products_to_display_this_page = all_products_for_current_selection[start_index:end_index]

    product_items_for_list = [{'id': prod['code'], 'name': prod['name']} for prod in products_to_display_this_page]
    user_states[sender]['current_product_list_offset'] = end_index

    # Botones de navegación de página y generales
    if start_index > 0:
        product_items_for_list.insert(0, {'id': NAV_ID_PREVIOUS_PAGE, 'name': '⬅️ Página Anterior'})
    if end_index < total_products:
        product_items_for_list.append({'id': NAV_ID_NEXT_PAGE, 'name': '➡️ Ver más productos'})

    if is_direct_from_category_no_subcat or \
            (subcategory_display_name_from_selection and subcategory_display_name_from_selection.strip().upper() in [
                "GENERAL (SIN SUBCATEGORÍA)", "SIN SUB CATEGORIA"]):
        product_items_for_list.append({'id': NAV_ID_BACK_TO_CATEGORIES, 'name': '↩️ Volver a Categorías'})
    else:
        product_items_for_list.append({'id': NAV_ID_BACK_TO_SUBCATEGORIES, 'name': '↩️ Volver a Subcategorías'})
    product_items_for_list.append({'id': NAV_ID_MAIN_MENU, 'name': '🏠 Menú Principal'})

    rows, product_map = create_list_rows_with_map(product_items_for_list, is_product_list=True)
    user_states[sender]['product_code_map'] = product_map

    total_pages = (total_products + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
    current_page_num = start_index // PRODUCTS_PER_PAGE + 1
    page_info = f"(Pág. {current_page_num} de {total_pages})" if total_pages > 1 else ""

    header = f"Productos en {effective_display_group_name[:15]} {page_info}"
    body = f"Elige un producto de '{effective_display_group_name[:30]}':"
    sections = [{"title": "Nuestros Productos 🛍️", "rows": rows}]

    response = send_interactive_list_message(sender, header, body, "Ver Productos", sections)
    if response and response.get('messages') and response['messages'][0].get('id'):
        user_states[sender]['state'] = STATE_AWAITING_PRODUCT_CHOICE
    else:
        send_message(sender, "¡Ups! No pude mostrar productos. 😕 ¿Volvemos a subcat?");
        user_states[sender][
            'state'] = STATE_AWAITING_SUBCATEGORY_CHOICE if not is_direct_from_category_no_subcat else STATE_AWAITING_CATEGORY_CHOICE
    print(f"DEBUG: ***** FIN display_products_list. Nuevo estado: {user_states[sender].get('state')} *****")


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    global token_is_invalid
    if token_is_invalid: print("Webhook BLOQUEADO: Token inválido."); return "Token inválido", 503
    if request.method == 'GET':
        if request.args.get('hub.verify_token') == VERIFY_TOKEN: return request.args.get('hub.challenge')
        return "Token incorrecto", 403

    elif request.method == 'POST':
        data = request.get_json()
        print("\n--- Nuevo Evento Webhook ---")
        sender = None
        try:
            if 'messages' in data['entry'][0]['changes'][0]['value']:
                message_data = data['entry'][0]['changes'][0]['value']['messages'][0]
                sender = message_data['from']
                message_type = message_data['type']

                if sender not in user_states: user_states[sender] = {}
                if not isinstance(user_states[sender], dict): user_states[sender] = {}
                if 'state' not in user_states[sender]: user_states[sender]['state'] = STATE_INITIAL

                current_state_info = user_states[sender]
                current_state = current_state_info['state']
                print(f"Usuario {sender} estado: {current_state}, datos guardados: {list(current_state_info.keys())}")

                if message_type == 'interactive':
                    interactive_data = message_data['interactive']
                    if interactive_data['type'] == 'button_reply':
                        button_reply_id = interactive_data['button_reply']['id']
                        print(f"Respuesta de botón: ID='{button_reply_id}'")

                        if current_state == STATE_AWAITING_PAYMENT_METHOD:
                            payment_method_text = ""
                            if button_reply_id == PAYMENT_ID_CASH:
                                payment_method_text = "Efectivo (con posible descuento)"
                            elif button_reply_id == PAYMENT_ID_TRANSFER:
                                payment_method_text = "Transferencia"
                            else:
                                send_message(sender, "Opción pago no reconocida. 🤔"); user_states[sender] = {
                                    'state': STATE_AWAITING_NEXT_ACTION}; return "OK", 200
                            user_states[sender]['selected_payment_method'] = payment_method_text
                            delivery_body = "¡Estupendo! Ahora, ¿cómo prefieres recibir tu pedido?\n\n🚚 Envío a domicilio\n🏪 Retiro en nuestro local"
                            delivery_buttons = [{'id': DELIVERY_ID_SHIP, 'title': 'Envío 🛵'},
                                                {'id': DELIVERY_ID_PICKUP, 'title': 'Retiro 🏪'}]
                            response = send_interactive_buttons_message(sender, delivery_body, delivery_buttons)
                            if response and response.get('messages') and response['messages'][0].get('id'):
                                user_states[sender]['state'] = STATE_AWAITING_DELIVERY_CHOICE
                            else:
                                send_message(sender, "Hubo un problema. Contacta a un vendedor (Opción 4).");
                                user_states[sender]['state'] = STATE_AWAITING_NEXT_ACTION

                        elif current_state == STATE_AWAITING_DELIVERY_CHOICE:
                            order_num = current_state_info.get('order_number_for_coordination', 'No especificado')
                            payment_method = current_state_info.get('selected_payment_method', 'No especificado')
                            if button_reply_id == DELIVERY_ID_PICKUP:
                                sales_msg_base = f"¡Hola! Te contacto de parte del asistente virtual de TecnoMundo. Pedido N° *{order_num}*. Forma de pago: *{payment_method}*. Opción: *Retiro en local*. Aguardo para coordinar. 😊"
                                send_message(sender,
                                             "¡Perfecto para el retiro! 👍 Un vendedor se contactará para coordinar.")
                                link = f"https://wa.me/{SALESPERSON_PHONE_NUMBER}?text={urllib.parse.quote(sales_msg_base)}"
                                send_message(sender, f"¡Listo! Te conectaremos con un vendedor:\n{link} 🙋‍♂️")
                                user_states[sender] = {'state': STATE_INITIAL};
                                for k in ['order_number_for_coordination', 'selected_payment_method']: user_states[
                                    sender].pop(k, None)
                            elif button_reply_id == DELIVERY_ID_SHIP:
                                user_states[sender]['delivery_type_for_coordination'] = "Envío a Domicilio"
                                send_message(sender,
                                             "Entendido. Para el envío, por favor, indícanos tu *dirección completa* (calle, número, barrio, ciudad): 🏠")
                                user_states[sender]['state'] = STATE_AWAITING_SHIPPING_ADDRESS
                            else:
                                send_message(sender, "Opción no reconocida. 🤔"); user_states[sender] = {
                                    'state': STATE_AWAITING_NEXT_ACTION}

                        elif current_state == STATE_AWAITING_POST_PRODUCT_ACTION:
                            product_code = current_state_info.get('last_selected_product_code', 'N/A')
                            product_name = current_state_info.get('last_selected_product_name', 'producto seleccionado')
                            product_page_url_from_state = current_state_info.get('last_selected_product_page_url', '')
                            if button_reply_id == POST_PRODUCT_CONTACT_SALES:
                                sales_msg = f"Hola, de parte del asistente virtual de TecnoMundo. Interés en: {product_name} (Cód: {product_code})."
                                if product_page_url_from_state: sales_msg += f" Link: {product_page_url_from_state}"
                                link = f"https://wa.me/{SALESPERSON_PHONE_NUMBER}?text={urllib.parse.quote(sales_msg)}"
                                send_message(sender,
                                             f"¡Perfecto! Para hablar con un vendedor sobre *{product_name}*, haz clic aquí:\n{link} 🙋‍♂️")
                                user_states[sender] = {'state': STATE_AWAITING_NEXT_ACTION}
                            elif button_reply_id == POST_PRODUCT_SEARCH_AGAIN:
                                send_message(sender, "¡Claro! Volvamos a la carga. 💪")
                                display_categories_list(sender)
                            elif button_reply_id == NAV_ID_MAIN_MENU:
                                send_message(sender, MAIN_MENU_MESSAGE)
                                user_states[sender] = {'state': STATE_AWAITING_NEXT_ACTION}
                            else:
                                send_message(sender, "Opción no reconocida. Volviendo al menú. 🤔")
                                send_message(sender, MAIN_MENU_MESSAGE)
                                user_states[sender] = {'state': STATE_AWAITING_NEXT_ACTION}
                            for key_to_pop in ['last_selected_product_code', 'last_selected_product_name',
                                               'last_selected_product_page_url', 'all_products_for_current_selection',
                                               'current_product_list_offset', 'current_selection_id_for_products',
                                               'current_products_details']:
                                user_states[sender].pop(key_to_pop, None)


                    elif interactive_data['type'] == 'list_reply':
                        whatsapp_list_reply_id = interactive_data['list_reply']['id']
                        selected_display_title = interactive_data['list_reply']['title']
                        print(
                            f"Respuesta lista: WA_ROW_ID='{whatsapp_list_reply_id}', Display='{selected_display_title}'")

                        if current_state == STATE_AWAITING_CATEGORY_CHOICE:
                            category_map = current_state_info.get('category_id_map', {})
                            selected_item_id_cat = category_map.get(whatsapp_list_reply_id)
                            print(
                                f"DEBUG webhook CatChoice: WA_ROW_ID='{whatsapp_list_reply_id}', Mapped DB_ID='{selected_item_id_cat}'")
                            if selected_item_id_cat is None:
                                print(
                                    f"Error CatListChoice: WA_ROW_ID '{whatsapp_list_reply_id}' no en mapa {category_map}");
                                display_categories_list(sender);
                                return "OK", 200
                            if selected_item_id_cat == NAV_ID_MAIN_MENU:
                                send_message(sender, MAIN_MENU_MESSAGE);
                                user_states[sender] = {'state': STATE_AWAITING_NEXT_ACTION};
                                return "OK", 200
                            selected_category_db_id = selected_item_id_cat
                            user_states[sender]['selected_category_id'] = selected_category_db_id
                            user_states[sender]['selected_category_name'] = selected_display_title
                            print(
                                f"Cat seleccionada (lista): DB_ID={selected_category_db_id}, DisplayName='{selected_display_title}'")
                            # Al seleccionar una categoría, limpiar datos de paginación de productos previos
                            user_states[sender].pop('all_products_for_current_selection', None)
                            user_states[sender].pop('current_product_list_offset', None)
                            display_subcategories_list(sender, selected_category_db_id, selected_display_title)

                        elif current_state == STATE_AWAITING_SUBCATEGORY_CHOICE:
                            subcategory_map = current_state_info.get('subcategory_id_map', {})
                            selected_item_id_subcat = subcategory_map.get(whatsapp_list_reply_id)
                            current_cat_id = current_state_info.get('selected_category_id');
                            current_cat_name = current_state_info.get('selected_category_name')
                            print(
                                f"DEBUG webhook SubCatChoice: WA_ROW_ID='{whatsapp_list_reply_id}', Mapped DB_ID='{selected_item_id_subcat}', CurrentCatID='{current_cat_id}'")
                            if selected_item_id_subcat is None or current_cat_id is None:
                                print(
                                    f"Error SubcatListChoice: WA_ROW_ID '{whatsapp_list_reply_id}' no en mapa {subcategory_map} o falta cat_id.");
                                display_categories_list(sender);
                                return "OK", 200
                            if selected_item_id_subcat == NAV_ID_MAIN_MENU:
                                send_message(sender, MAIN_MENU_MESSAGE);
                                user_states[sender] = {'state': STATE_AWAITING_NEXT_ACTION};
                                return "OK", 200
                            selected_subcategory_db_id = selected_item_id_subcat
                            user_states[sender]['selected_subcategory_id'] = selected_subcategory_db_id
                            user_states[sender]['selected_subcategory_name'] = selected_display_title
                            print(
                                f"SubCat seleccionada (lista): DB_ID={selected_subcategory_db_id}, DisplayName='{selected_display_title}'")
                            user_states[sender].pop('all_products_for_current_selection',
                                                    None)  # Limpiar productos al cambiar subcategoría
                            user_states[sender].pop('current_product_list_offset', None)
                            display_products_list(sender, current_cat_id, current_cat_name, selected_subcategory_db_id,
                                                  selected_display_title, page_offset=0)

                        elif current_state == STATE_AWAITING_PRODUCT_CHOICE:
                            product_map = current_state_info.get('product_code_map', {});
                            selected_item_id_prod = product_map.get(whatsapp_list_reply_id)
                            current_cat_id = current_state_info.get('selected_category_id');
                            current_cat_name = current_state_info.get('selected_category_name')
                            current_subcat_id = current_state_info.get('selected_subcategory_id')
                            current_subcat_name = current_state_info.get('selected_subcategory_name')

                            if selected_item_id_prod is None:
                                print(
                                    f"Error ProdListChoice: WA_ROW_ID '{whatsapp_list_reply_id}' no en mapa {product_map}.");
                                if current_cat_id and current_cat_name:
                                    display_subcategories_list(sender, current_cat_id, current_cat_name)
                                else:
                                    display_categories_list(sender)
                                return "OK", 200

                            if selected_item_id_prod == NAV_ID_MAIN_MENU:
                                send_message(sender, MAIN_MENU_MESSAGE); user_states[sender] = {
                                    'state': STATE_AWAITING_NEXT_ACTION}
                            elif selected_item_id_prod == NAV_ID_BACK_TO_CATEGORIES:
                                display_categories_list(sender)
                            elif selected_item_id_prod == NAV_ID_BACK_TO_SUBCATEGORIES:
                                if current_cat_id and current_cat_name:
                                    display_subcategories_list(sender, current_cat_id, current_cat_name)
                                else:
                                    display_categories_list(sender)
                            elif selected_item_id_prod == NAV_ID_NEXT_PAGE:
                                current_offset = current_state_info.get('current_product_list_offset', 0)
                                display_products_list(sender, current_cat_id, current_cat_name, current_subcat_id,
                                                      current_subcat_name, page_offset=current_offset)
                            elif selected_item_id_prod == NAV_ID_PREVIOUS_PAGE:
                                current_offset = current_state_info.get('current_product_list_offset',
                                                                        PRODUCTS_PER_PAGE)
                                prev_offset = max(0, current_offset - (2 * PRODUCTS_PER_PAGE))
                                display_products_list(sender, current_cat_id, current_cat_name, current_subcat_id,
                                                      current_subcat_name, page_offset=prev_offset)
                            else:
                                product_code = selected_item_id_prod
                                product_details_map = current_state_info.get('current_products_details', {})
                                product_data = product_details_map.get(product_code)
                                if not product_data:
                                    send_message(sender,
                                                 "Lo siento, no pude obtener los detalles completos de ese producto. 😕");
                                    user_states[sender]['state'] = STATE_AWAITING_NEXT_ACTION;
                                    return "OK", 200
                                product_full_name = product_data.get('name', selected_display_title)
                                product_page_url = product_data.get(
                                    'page_url')  # URL de la página del producto desde la DB

                                # Mensaje 1: Info del producto y enlace web
                                product_info_message = f"✨ Seleccionaste: *{product_full_name}* (Cód: {product_code})."
                                if product_page_url and product_page_url.startswith("http"):
                                    product_info_message += f"\n\n🌐 Puedes verlo en nuestra web aquí:\n{product_page_url}"
                                else:
                                    print(
                                        f"ADVERTENCIA: product_page_url inválida para {product_code}: {product_page_url}"); product_page_url = ""
                                send_message(sender, product_info_message)
                                user_states[sender]['last_selected_product_code'] = product_code
                                user_states[sender]['last_selected_product_name'] = product_full_name
                                user_states[sender]['last_selected_product_page_url'] = product_page_url
                                post_product_body = "¿Qué te gustaría hacer a continuación? 😊"
                                post_product_buttons = [
                                    {'id': POST_PRODUCT_CONTACT_SALES, 'title': 'Contactar Vendedor 🙋‍♂️'},
                                    {'id': POST_PRODUCT_SEARCH_AGAIN, 'title': 'Buscar Otro 🛍️'},
                                    {'id': NAV_ID_MAIN_MENU, 'title': '🏠 Menú Principal'}
                                ]
                                response_btns = send_interactive_buttons_message(sender, post_product_body,
                                                                                 post_product_buttons)
                                if response_btns and response_btns.get('messages') and response_btns['messages'][0].get(
                                        'id'):
                                    user_states[sender]['state'] = STATE_AWAITING_POST_PRODUCT_ACTION
                                else:
                                    send_message(sender, "Si necesitas algo más, escribe 'menú'."); user_states[sender][
                                        'state'] = STATE_AWAITING_NEXT_ACTION


                elif message_type == 'text':
                    text_original = message_data['text']['body']
                    text_normalized = normalize_text(text_original)
                    print(f"Texto recibido: '{text_original}' (Normalizado: '{text_normalized}')")

                    if current_state == STATE_INITIAL:
                        if text_normalized in ['hola', 'menu', 'buenas', 'ayuda', 'comenzar']:
                            send_message(sender, MAIN_MENU_MESSAGE);
                            user_states[sender]['state'] = STATE_AWAITING_NEXT_ACTION
                        else:
                            send_message(sender, "No entendí. " + MAIN_MENU_MESSAGE); user_states[sender][
                                'state'] = STATE_AWAITING_NEXT_ACTION

                    elif current_state == STATE_AWAITING_NEXT_ACTION:
                        keys_to_clean = ['category_id_map', 'subcategory_id_map', 'product_code_map',
                                         'selected_category_id', 'selected_category_name', 'selected_subcategory_id',
                                         'selected_subcategory_name', 'current_products_details',
                                         'current_products_full_names', 'order_number_for_coordination',
                                         'selected_payment_method', 'delivery_type_for_coordination',
                                         'shipping_address_for_coordination', 'last_selected_product_code',
                                         'last_selected_product_name', 'last_selected_product_page_url',
                                         'all_products_for_current_selection', 'current_product_list_offset',
                                         'current_selection_id_for_products']
                        for key in keys_to_clean: user_states[sender].pop(key, None)
                        if '1' == text_original.strip():
                            send_message(sender,
                                         "¡Perfecto! Para coordinar tu envío/retiro y pago, primero necesito tu *número de orden de pedido*. 🔢\nLo puedes encontrar en el correo de confirmación que recibiste al realizar tu compra. Un vendedor verificará estos datos luego. 😊")
                            user_states[sender]['state'] = STATE_ASKING_ORDER_NUMBER_FOR_COORDINATION
                        elif '2' == text_original.strip():
                            user_states[sender].pop('all_products_for_current_selection', None)
                            user_states[sender].pop('current_product_list_offset', None)
                            display_categories_list(sender)
                        elif '4' == text_original.strip():
                            link = f"https://wa.me/{SALESPERSON_PHONE_NUMBER}?text={urllib.parse.quote('¡Hola! El asistente virtual de TecnoMundo me recomendó hablar con ustedes. 👋')}"
                            send_message(sender, f"¡Claro! Para hablar con un vendedor, haz clic aquí:\n{link} 🙋‍♂️");
                            user_states[sender]['state'] = STATE_INITIAL
                        elif '3' == text_original.strip():
                            send_message(sender,
                                         "Lamento que tengas un inconveniente. 😟 Por favor, describe brevemente tu problema para que podamos ayudarte:")
                            user_states[sender]['state'] = STATE_AWAITING_PROBLEM_DESCRIPTION
                        else:
                            send_message(sender,
                                         "Hmm, no reconozco esa opción. 🤔 Elige un número del menú.\n\n" + MAIN_MENU_MESSAGE)

                    elif current_state == STATE_AWAITING_PROBLEM_DESCRIPTION:
                        problem_description = text_original.strip()
                        if len(problem_description) < 10:
                            send_message(sender,
                                         "Por favor, describe tu problema con un poco más de detalle para que podamos entender mejor. 🙏")
                        else:
                            sales_msg = (
                                f"¡Hola! Te contacto de parte del asistente virtual de TecnoMundo.\n\nProblema: '{problem_description}'\n\nEspero respuesta a la brevedad. Gracias.")
                            encoded_msg = urllib.parse.quote(sales_msg)
                            whatsapp_link = f"https://wa.me/{SALESPERSON_PHONE_NUMBER}?text={encoded_msg}"
                            send_message(sender,
                                         f"Gracias por describir tu problema. Hemos notificado a un representante. Si es urgente, puedes contactarlos directamente aquí:\n{whatsapp_link}")
                            user_states[sender]['state'] = STATE_AWAITING_NEXT_ACTION

                    elif current_state == STATE_ASKING_ORDER_NUMBER_FOR_COORDINATION:
                        order_input = text_original.strip()
                        if order_input.isdigit() and len(order_input) > 1:
                            user_states[sender]['order_number_for_coordination'] = order_input
                            payment_body = f"¡Gracias por el N° de orden *{order_input}*! 😊\n\nAhora, ¿cómo te gustaría abonar? Recuerda que pagando en *efectivo* puedes tener ¡hasta un *10% de descuento*! 🤑"
                            buttons = [{'id': PAYMENT_ID_CASH, 'title': 'Efectivo 💵'},
                                       {'id': PAYMENT_ID_TRANSFER, 'title': 'Transferencia 💳'}]
                            response = send_interactive_buttons_message(sender, payment_body, buttons)
                            if response and response.get('messages') and response['messages'][0].get('id'):
                                user_states[sender]['state'] = STATE_AWAITING_PAYMENT_METHOD
                            else:
                                send_message(sender, "Hubo un problema. Contacta a un vendedor (Opción 4).");
                                user_states[sender]['state'] = STATE_AWAITING_NEXT_ACTION
                        else:
                            send_message(sender,
                                         "N° de orden no válido (solo números, >1 dígito). 🤔 Intenta de nuevo o 'menú'.")

                    elif current_state == STATE_AWAITING_SHIPPING_ADDRESS:
                        shipping_address = text_original.strip()
                        if len(shipping_address) < 5:
                            send_message(sender,
                                         "La dirección parece muy corta. 🤔 Por favor, ingresa una dirección más completa o escribe 'menú' para cancelar.")
                        else:
                            user_states[sender]['shipping_address_for_coordination'] = shipping_address
                            order_num = current_state_info.get('order_number_for_coordination', 'N/E')
                            payment_method = current_state_info.get('selected_payment_method', 'N/E')
                            delivery_type = current_state_info.get('delivery_type_for_coordination', 'Envío')
                            sales_msg_base = f"¡Hola! Te contacto de parte del asistente virtual de TecnoMundo. Pedido N° *{order_num}*. Forma de pago: *{payment_method}*. Opción: *{delivery_type}*. Dirección para envío: *{shipping_address}*. Aguardo para coordinar costo de envío (si aplica) y entrega. Gracias 😊"
                            shipping_conditions_reminder = (
                                "Te recuerdo nuestras condiciones de envío provincial:\n"
                                "▪️ Pedidos de $100.000 o más: ¡Envío *GRATIS*! 🎉\n"
                                "▪️ Pedidos entre $50.000 y $99.999: Envío con recargo (a confirmar por el vendedor según zona).\n"
                                "▪️ Pedidos menores a $50.000: Solo retiro en nuestro local.\n\n"
                                "Un vendedor confirmará todo contigo. 😉"
                            )
                            send_message(sender, shipping_conditions_reminder)
                            link = f"https://wa.me/{SALESPERSON_PHONE_NUMBER}?text={urllib.parse.quote(sales_msg_base)}"
                            send_message(sender,
                                         f"¡Gracias por la dirección! Te conectaremos con un vendedor:\n{link} 🙋‍♂️")
                            user_states[sender] = {'state': STATE_INITIAL};
                            for k_ in ['order_number_for_coordination', 'selected_payment_method',
                                       'delivery_type_for_coordination', 'shipping_address_for_coordination']:
                                user_states[sender].pop(k_, None)

                    elif current_state in [STATE_AWAITING_CATEGORY_CHOICE, STATE_AWAITING_SUBCATEGORY_CHOICE,
                                           STATE_AWAITING_PRODUCT_CHOICE, STATE_AWAITING_PAYMENT_METHOD,
                                           STATE_AWAITING_DELIVERY_CHOICE, STATE_AWAITING_POST_PRODUCT_ACTION]:
                        if text_normalized == "menu":
                            send_message(sender, MAIN_MENU_MESSAGE); user_states[sender] = {
                                'state': STATE_AWAITING_NEXT_ACTION}
                        else:
                            send_message(sender, "Por favor, usa la lista o los botones. 😉 Escribe 'menú' para volver.")
            return "Evento recibido", 200
        except Exception as e:
            print(f"--- ERROR WEBHOOK RAÍZ ---");
            error_sender_id = sender if sender else "desconocido"
            print(f"Error para {error_sender_id}: {e}");
            traceback.print_exc()
            if sender and not token_is_invalid:
                try:
                    send_message(sender, "¡Ups! Algo no salió bien. 🛠️ Intenta de nuevo o 'menú'.")
                except:
                    pass
            if sender and sender in user_states: user_states[sender] = {'state': STATE_INITIAL, 'error_context': str(e)}
            return "Error interno", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
