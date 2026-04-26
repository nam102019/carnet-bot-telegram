#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Bot Vitrine - Carnet de Sauvegarde
✅ Boutons 100% fonctionnels + Affichage listes corrigé + Export CSV sécurisé
"""

import logging
import os
import csv
import io
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, ConversationHandler, MessageHandler, filters
)
from telegram.request import HTTPXRequest

# Import PostgreSQL
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    pass

# Configuration Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 🔑 Token
TOKEN = os.getenv("TELEGRAM_TOKEN")

# 🗄️ Base de données
DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None

# 📋 Catégories
CATEGORIES = {
    "1xbet": {"emoji": "🔵", "subs": ["Partenaire promo code", "Agent Mobcash"]},
    "Afropari": {"emoji": "🟣", "subs": ["Partenaire promo code", "Agent Mobcash"]},
    "Melbet": {"emoji": "🟡", "subs": ["Partenaire promo code", "Agent Mobcash"]}
}

# 📱 Menu permanent en bas
QUICK_MENU = ReplyKeyboardMarkup([
    ["🔵 1xbet", "🟣 Afropari", "🟡 Melbet"],
    ["➕ Ajouter", "📋 Voir fiches", "📤 Exporter"],
    ["🏠 Accueil", "❓ Aide"]
], resize_keyboard=True, is_persistent=True)

# 🎯 Filtres STRICTS
MENU_TEXTS = {"🔵 1xbet", "🟣 Afropari", "🟡 Melbet", "➕ Ajouter", "📋 Voir fiches", "📤 Exporter", "🏠 Accueil", "❓ Aide"}
MENU_FILTER = filters.Regex(r'^(🔵 1xbet|🟣 Afropari|🟡 Melbet|➕ Ajouter| Voir fiches|📤 Exporter|🏠 Accueil|❓ Aide)$')
INPUT_FILTER = filters.TEXT & ~filters.COMMAND & ~MENU_FILTER

# États
STATE_PRENOM, STATE_NOM, STATE_CONTENT, STATE_EDIT = range(4)
user_sessions = {}

def get_db_connection():
    return psycopg2.connect(DATABASE_URL) if USE_POSTGRES else sqlite3.connect("carnet_vitrine.db")

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute('''CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY, category TEXT NOT NULL, subcategory TEXT NOT NULL,
            prenom TEXT NOT NULL, nom TEXT NOT NULL, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    else:
        cur.execute('''CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, subcategory TEXT NOT NULL,
            prenom TEXT NOT NULL, nom TEXT NOT NULL, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    cur.close(); conn.close()
    logger.info(f"✅ DB initialisée : {'PostgreSQL ✅' if USE_POSTGRES else 'SQLite'}")

# ==================== 🏠 MENU RAPIDE ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 *Bienvenue !*\n\n🏪 Utilisez le menu en bas.", reply_markup=QUICK_MENU, parse_mode="Markdown")

async def handle_quick_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if context.user_data.get('conv_active'): context.user_data.clear()

    if text in {"🔵 1xbet", "🟣 Afropari", "🟡 Melbet"}:
        cat = text.split(" ", 1)[1]
        kb = [[InlineKeyboardButton(f"📄 {sub}", callback_data=f"sub_{cat}_{sub.replace(' ', '_')}")] for sub in CATEGORIES[cat]["subs"]]
        kb.append([InlineKeyboardButton("🔙 Retour", callback_data="main")])
        await update.message.reply_text(f"📂 *{cat.upper()}*\n\nSélectionnez une section :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "➕ Ajouter":
        kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c}", callback_data=f"add_{c}_{CATEGORIES[c]['subs'][0].replace(' ', '_')}")] for c in CATEGORIES]
        await update.message.reply_text("➕ *Ajouter*\n\nChoisissez une catégorie :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "📋 Voir fiches":
        # ✅ CORRECTION : Affiche TOUTES les fiches de la catégorie (peu importe la sous-catégorie)
        kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c} (Tout voir)", callback_data=f"list_{c}")] for c in CATEGORIES]
        await update.message.reply_text("📋 *Voir les fiches*\n\nChoisissez une catégorie :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "📤 Exporter":
        kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c} (Tout exporter)", callback_data=f"export_{c}")] for c in CATEGORIES]
        await update.message.reply_text("📤 *Exporter CSV*\n\nChoisissez une catégorie :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "🏠 Accueil":
        kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c}", callback_data=f"cat_{c}")] for c in CATEGORIES]
        await update.message.reply_text("🏪 *CATÉGORIES*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        
    elif text == "❓ Aide":
        await update.message.reply_text("❓ *Aide*\n\n• Menu en bas permanent\n• Fiches triées par nom/prénom\n• ✏️ Modifie directement le texte\n• 📤 Export CSV compatible Excel", parse_mode="Markdown")

# ==================== NAVIGATION INLINE ====================
async def show_vitrine_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [[InlineKeyboardButton(f"{CATEGORIES[c]['emoji']} {c}", callback_data=f"cat_{c}")] for c in CATEGORIES]
    await query.edit_message_text("🏪 *CATÉGORIES*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def category_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat = query.data.replace("cat_", "")
    kb = [[InlineKeyboardButton(f"📄 {sub}", callback_data=f"sub_{cat}_{sub.replace(' ', '_')}")] for sub in CATEGORIES[cat]["subs"]]
    kb.append([InlineKeyboardButton("🔙 Retour", callback_data="main")])
    await query.edit_message_text(f"📂 *{cat.upper()}*\n\nSélectionnez :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def subcategory_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat, sub = parts[1], parts[2].replace("_", " ")
    kb = [
        [InlineKeyboardButton("➕ Ajouter", callback_data=f"add_{cat}_{parts[2]}")],
        [InlineKeyboardButton("📋 Voir", callback_data=f"list_{cat}_{parts[2]}")],
        [InlineKeyboardButton("🔙 Retour", callback_data=f"cat_{cat}")]
    ]
    await query.edit_message_text(f"📂 {cat}\n📄 {sub}\n\nAction :", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ==================== ➕ AJOUT ====================
async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['conv_active'] = True
    parts = query.data.split("_", 2)
    user_sessions[query.from_user.id] = {"cat": parts[1], "sub": parts[2].replace("_", " "), "step": "prenom"}
    await query.edit_message_text(f"➕ *NOUVELLE FICHE*\n\n*1/3 Prénom :*", parse_mode="Markdown")
    return STATE_PRENOM

async def get_prenom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_sessions[uid]["prenom"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Prénom OK.\n\n*2/3 Nom :*", parse_mode="Markdown")
    return STATE_NOM

async def get_nom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_sessions[uid]["nom"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Nom OK.\n\n*3/3 Contenu :*", parse_mode="Markdown")
    return STATE_CONTENT

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sess = user_sessions.get(uid)
    if not sess: return ConversationHandler.END
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO notes (category, subcategory, prenom, nom, content) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (sess["cat"], sess["sub"], sess["prenom"], sess["nom"], update.message.text))
    conn.commit()
    nid = cur.fetchone()[0]
    cur.close(); conn.close()
    del user_sessions[uid]
    context.user_data.pop('conv_active', None)
    
    await update.message.reply_text(f"✅ *FICHE AJOUTÉE !*\n🆔 `{nid}`\n👤 {sess['prenom']} {sess['nom']}\n💾 Sauvegardé.", parse_mode="Markdown")
    return ConversationHandler.END

# ==================== 📋 LISTE (CORRIGÉE) ====================
async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat = parts[1]
    sub = parts[2].replace("_", " ") if len(parts) > 2 else None
    
    conn = get_db_connection()
    cur = conn.cursor()
    if sub:
        cur.execute("SELECT id, prenom, nom, content FROM notes WHERE category=%s AND subcategory=%s ORDER BY nom, prenom", (cat, sub))
    else:
        cur.execute("SELECT id, prenom, nom, content FROM notes WHERE category=%s ORDER BY nom, prenom", (cat,))
    notes = cur.fetchall()
    cur.close(); conn.close()
    
    if not notes:
        msg = f"📭 *Aucune fiche*\n📂 {cat}" + (f" → {sub}" if sub else "")
        await query.edit_message_text(msg, parse_mode="Markdown")
        return
    
    text = f"📋 *LISTE*\n📂 {cat}" + (f" → {sub}" if sub else " (Tout)") + "\n─────────────\n\n"
    kb = []
    for nid, p, n, c in notes:
        text += f"🔹 *{p} {n}*\n   `{c[:30]}...`\n\n"
        kb.append([InlineKeyboardButton(f"👤 {p} {n}", callback_data=f"view_{nid}")])
    
    back_cb = f"sub_{cat}_{sub.replace(' ', '_')}" if sub else f"cat_{cat}"
    kb.append([InlineKeyboardButton("🔙 Retour", callback_data=back_cb)])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ==================== 👁️ DÉTAIL ====================
async def view_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[1])
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM notes WHERE id=%s", (nid,))
    note = cur.fetchone()
    cur.close(); conn.close()
    if not note: return await query.edit_message_text("❌ Introuvable.", parse_mode="Markdown")
    
    # Gestion propre de la date (datetime objet vs string)
    date_str = note[6].strftime("%d/%m/%Y %H:%M") if isinstance(note[6], datetime) else str(note[6])[:16]
    
    text = f"🆔 ID: `{note[0]}`\n📂 {note[1]} → {note[2]}\n👤 *{note[3]} {note[4]}*\n📝 *Contenu :*\n`{note[5]}`\n🕒 {date_str}"
    kb = [
        [InlineKeyboardButton("✏️ Modifier", callback_data=f"edit_{nid}")],
        [InlineKeyboardButton("🗑️ Supprimer", callback_data=f"del_{nid}")],
        [InlineKeyboardButton("🔙 Retour", callback_data=f"list_{note[1]}_{note[2].replace(' ', '_')}")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ==================== ✏️ MODIFICATION ====================
async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['conv_active'] = True
    nid = int(query.data.split("_")[1])
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT content, category, subcategory FROM notes WHERE id=%s", (nid,))
    res = cur.fetchone()
    cur.close(); conn.close()
    if not res: return await query.edit_message_text("❌ Introuvable.", parse_mode="Markdown")
    
    content, cat, sub = res
    context.user_data.update({'edit_id': nid, 'cat': cat, 'sub': sub})
    preview = content if len(content) < 300 else content[:300] + "..."
    
    await query.edit_message_text(f"✏️ *MODIFICATION*\n📂 {cat} → {sub}\n\n📝 *Actuel :*\n`{preview}`\n\n👇 *Envoyez le NOUVEAU texte :*", parse_mode="Markdown")
    return STATE_EDIT

async def save_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nid = context.user_data.get('edit_id')
    cat, sub = context.user_data.get('cat'), context.user_data.get('sub')
    if not nid: return ConversationHandler.END
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notes SET content=%s WHERE id=%s", (update.message.text, nid))
    conn.commit()
    cur.close(); conn.close()
    
    context.user_data.pop('conv_active', None)
    context.user_data.clear()
    await update.message.reply_text(f"✅ *MODIFIÉE !*\n🆔 `{nid}`\n📂 {cat} → {sub}\n💾 Sauvegardé.", parse_mode="Markdown")
    return ConversationHandler.END

# ==================== 🗑️ SUPPRESSION ====================
async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[1])
    kb = [[InlineKeyboardButton("✅ Oui", callback_data=f"exec_del_{nid}")], [InlineKeyboardButton("❌ Non", callback_data=f"view_{nid}")]]
    await query.edit_message_text("⚠️ *SUPPRIMER ?*\n\nAction irréversible.", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def exec_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    nid = int(query.data.split("_")[2])
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id=%s", (nid,))
    conn.commit()
    cur.close(); conn.close()
    await query.edit_message_text(f"🗑️ *SUPPRIMÉE !*\n🆔 `{nid}`\n💾 Base mise à jour.", parse_mode="Markdown")

# ==================== 📤 EXPORT (CORRIGÉ) ====================
async def export_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    cat = parts[1]
    sub = parts[2].replace("_", " ") if len(parts) > 2 else None
    
    conn = get_db_connection()
    cur = conn.cursor()
    if sub:
        cur.execute("SELECT prenom, nom, subcategory, content, created_at FROM notes WHERE category=%s AND subcategory=%s ORDER BY nom, prenom", (cat, sub))
    else:
        cur.execute("SELECT prenom, nom, subcategory, content, created_at FROM notes WHERE category=%s ORDER BY nom, prenom", (cat,))
    notes = cur.fetchall()
    cur.close(); conn.close()
    
    if not notes:
        await query.edit_message_text("📭 Aucune donnée à exporter.")
        return
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)
    writer.writerow(['Prénom', 'Nom', 'Sous-catégorie', 'Contenu', 'Date'])
    
    for row in notes:
        # Conversion sécurisée de la date
        date_val = row[4].strftime("%d/%m/%Y %H:%M") if isinstance(row[4], datetime) else str(row[4])
        writer.writerow([row[0], row[1], row[2], row[3], date_val])
    
    csv_bytes = output.getvalue().encode('utf-8-sig')
    file_io = io.BytesIO(csv_bytes)
    file_io.name = f"Export_{cat}_{sub.replace(' ', '_') if sub else 'Tout'}.csv"
    
    await query.message.reply_document(document=file_io, caption=f"📊 *EXPORT*\n{cat}" + (f" → {sub}" if sub else " (Tout)") + f"\n{len(notes)} fiche(s)", parse_mode="Markdown")
    await query.edit_message_text("✅ *Export envoyé ! Fichier ci-dessus.*", parse_mode="Markdown")

# ==================== 🚀 POINT D'ENTRÉE ====================
def main():
    init_db()
    logger.info("🚀 Démarrage...")
    
    app = Application.builder().token(TOKEN).build()
    
    # 1. Menu & Commandes
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(MENU_FILTER, handle_quick_menu))
    
    # 2. Callbacks
    app.add_handler(CallbackQueryHandler(show_vitrine_menu, pattern="^main$"))
    app.add_handler(CallbackQueryHandler(category_view, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(subcategory_view, pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(show_list, pattern="^list_"))
    app.add_handler(CallbackQueryHandler(view_detail, pattern="^view_"))
    app.add_handler(CallbackQueryHandler(confirm_delete, pattern="^del_"))
    app.add_handler(CallbackQueryHandler(exec_delete, pattern="^exec_del_"))
    app.add_handler(CallbackQueryHandler(export_csv, pattern="^export_"))
    
    # 3. Conversations
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add, pattern="^add_")],
        states={
            STATE_PRENOM: [MessageHandler(INPUT_FILTER, get_prenom)],
            STATE_NOM: [MessageHandler(INPUT_FILTER, get_nom)],
            STATE_CONTENT: [MessageHandler(INPUT_FILTER, save_note)],
        }, fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)], name="add"
    ))
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit, pattern="^edit_")],
        states={STATE_EDIT: [MessageHandler(INPUT_FILTER, save_edit)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)], name="edit"
    ))
    
    logger.info("✅ Prêt !")
    print("🤖 Bot démarré. Listes & Export corrigés.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
