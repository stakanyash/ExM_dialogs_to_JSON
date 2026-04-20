# Dialogs parser to JSON by stakanyash
# Supports dialogsglobal.xml and strings.xml
# dynamicdialogsglobal.xml currently are not supported

# Imports

import re
import json
import os
import logging
import easygui
from collections import defaultdict
from lxml import etree as ET

# Logging setup

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Extracts dialogs from strings.xml

def extract_strings_dialogues(xml_path):
    try:
        with open(xml_path, "rb") as f:
            xml_data = f.read()
    except OSError as e:
        logging.error(f"Не удалось открыть файл: {e}")
        return None

    try:
        root = ET.fromstring(xml_data)
        if root.tag != "resource" or root.find("string") is None:
            logging.error("Файл не является файлом диалогов.")
            return None
    except ET.XMLSyntaxError as e:
        logging.error(f"Ошибка парсинга XML: {e}")
        return None

    dialogues_by_character = defaultdict(list)

    for string in root.iter("string"):
        value = string.get("value")
        if not value:
            continue

        if string.get("numButtons", "0") != "0":
            dialogues_by_character["УВЕДОМЛЕНИЕ"].append(value)
            continue

        model_name = string.get("modelName", "")
        msg_type = string.get("msgType", "")

        if "|" in value:
            name, text = value.split("|", 1)
            name = name.strip()
            text = text.strip()

            if msg_type == "SCROLL":
                name = "SCROLL текст"
            elif not name:
                name = model_name or "UNKNOWN"
        else:
            if not model_name:
                continue
            name = model_name
            text = value.strip()

        if not text:
            continue

        dialogues_by_character[name].append(text)

    return dialogues_by_character

# Finding game root folder

def find_game_root(dialogs_path):
    path = os.path.abspath(dialogs_path)
    while True:
        parent = os.path.dirname(path)
        if parent == path:
            return None
        if os.path.isdir(os.path.join(parent, "data")):
            return parent
        path = parent

# Checking object names for NPC name

def load_object_names(maps_folder):
    names = {}
    if not os.path.isdir(maps_folder):
        return names

    for map_dir in os.listdir(maps_folder):
        map_path = os.path.join(maps_folder, map_dir)
        if not os.path.isdir(map_path):
            continue

        obj_names_path = os.path.join(map_path, "object_names.xml")
        if not os.path.isfile(obj_names_path):
            continue

        try:
            with open(obj_names_path, "rb") as f:
                data = f.read()
            if not data.strip():
                continue
            tree = ET.fromstring(data)
            for obj in tree.iter("Object"):
                tech_name = obj.get("Name")
                full_name = obj.get("FullName", tech_name)
                if tech_name:
                    names[tech_name] = (full_name, map_path)
        except ET.XMLSyntaxError as e:
            logging.warning(f"Ошибка парсинга {obj_names_path}: {e}")

    return names

# Loading hello replies

def load_hello_replies(maps_folder):
    hello_map = {}
    if not os.path.isdir(maps_folder):
        return hello_map

    for map_dir in os.listdir(maps_folder):
        map_path = os.path.join(maps_folder, map_dir)
        if not os.path.isdir(map_path):
            continue

        scene_path = os.path.join(map_path, "dynamicscene.xml")
        if not os.path.isfile(scene_path):
            continue

        try:
            with open(scene_path, "rb") as f:
                data = f.read()
            if not data.strip():
                continue
            tree = ET.fromstring(data)
            for obj in tree.iter("Object"):
                hello_replies = obj.get("helloReplyNames", "")
                if not hello_replies:
                    continue
                tech_name = obj.get("Name", "UNKNOWN")
                for reply_name in hello_replies.split():
                    hello_map[reply_name] = (tech_name, map_path)
        except ET.XMLSyntaxError as e:
            logging.warning(f"Ошибка парсинга {scene_path}: {e}")

    return hello_map

# Checking for StartConversation in dialogs

def extract_start_conversation(script_result):
    if not script_result:
        return None
    match = re.search(r'StartConversation\([\'"]([^\'"]+)[\'"]\)', script_result)
    return match.group(1) if match else None

# Extracts all dialogs from dialogsglobal.xml

def extract_dialogs_global(xml_path):
    try:
        with open(xml_path, "rb") as f:
            xml_data = f.read()
    except OSError as e:
        logging.error(f"Не удалось открыть файл: {e}")
        return None

    try:
        root = ET.fromstring(xml_data)
        if root.tag != "DialogsResource" or root.find("Reply") is None:
            logging.error("Файл не является файлом диалогов города.")
            return None
    except ET.XMLSyntaxError as e:
        logging.error(f"Ошибка парсинга XML: {e}")
        return None

    game_root = find_game_root(xml_path)
    if not game_root:
        logging.error("Не удалось определить корневую папку игры.")
        return None

    maps_folder = os.path.join(game_root, "data", "maps")
    logging.info(f"Папка карт: {maps_folder}")

    object_names = load_object_names(maps_folder)   # { tech_name: (full_name, map_path) }
    hello_replies = load_hello_replies(maps_folder)  # { reply_name: (tech_name, map_path) }

    all_replies = {}
    for reply in root.iter("Reply"):
        name = reply.get("name")
        if name:
            all_replies[name] = reply

    def resolve_display_name(tech_name):
        if tech_name in object_names:
            return object_names[tech_name][0]
        return tech_name

    def walk_branch(reply_name, current_npc_tech, current_map_path, visited, branch):
        if reply_name in visited:
            return [branch]
        visited = visited | {reply_name}

        reply = all_replies.get(reply_name)
        if reply is None:
            return [branch]

        role = reply.get("role", "")
        text = reply.get("text", "").strip()
        script_result = reply.get("scriptResult", "")

        new_npc = extract_start_conversation(script_result)
        if new_npc:
            current_npc_tech = new_npc
            for r_name, (tech, m_path) in hello_replies.items():
                if tech == new_npc and m_path == current_map_path:
                    current_map_path = m_path
                    break

        if text:
            speaker = "ИГРОК" if role == "PLAYER" else resolve_display_name(current_npc_tech)
            branch = branch + [{"speaker": speaker, "text": text}]

        next_replies = [r for r in reply.get("nextReplies", "").split() if r]

        if not next_replies:
            return [branch]

        if len(next_replies) == 1:
            return walk_branch(next_replies[0], current_npc_tech, current_map_path, visited, branch)

        all_branches = []
        for next_name in next_replies:
            sub_branches = walk_branch(next_name, current_npc_tech, current_map_path, visited, branch)
            all_branches.extend(sub_branches)

        return all_branches

    global_visited = set()
    dialogs = {}

    for hello_name, (tech_name, map_path) in hello_replies.items():
        if hello_name not in all_replies:
            continue
        if hello_name in global_visited:
            continue

        branches = walk_branch(hello_name, tech_name, map_path, set(), [])
        branches = [b for b in branches if b]
        if not branches:
            continue

        def collect_visited(reply_name, acc):
            if reply_name in acc:
                return
            acc.add(reply_name)
            reply = all_replies.get(reply_name)
            if reply is None:
                return
            for next_name in reply.get("nextReplies", "").split():
                if next_name:
                    collect_visited(next_name, acc)

        collect_visited(hello_name, global_visited)

        if len(branches) == 1:
            dialogs[hello_name] = branches[0]
        else:
            for i, branch in enumerate(branches):
                dialogs[f"{hello_name}_{i}"] = branch

    return dialogs

# Detects file type (dialogs or strings)

def detect_file_type(xml_path):
    try:
        with open(xml_path, "rb") as f:
            tree = ET.parse(f)
        root = tree.getroot()
        if root.tag == "resource" and root.find("string") is not None:
            return "strings"
        if root.tag == "DialogsResource" and root.find("Reply") is not None:
            return "dialogs_global"
        return None
    except ET.XMLSyntaxError:
        return None

# Calculating total stats

def calculate_stats(data, file_type):
    stats = defaultdict(lambda: {"replicas": 0, "words": 0, "characters": 0})

    if file_type == "strings":
        for name, replicas in data.items():
            for text in replicas:
                stats[name]["replicas"] += 1
                stats[name]["words"] += len(text.split())
                stats[name]["characters"] += len(text)
    else:
        for dialog in data.values():
            for entry in dialog:
                speaker = entry["speaker"]
                text = entry["text"]
                stats[speaker]["replicas"] += 1
                stats[speaker]["words"] += len(text.split())
                stats[speaker]["characters"] += len(text)

    return dict(stats)

# Asks for xml file

def select_file():
    return easygui.fileopenbox(
        title="Выберите XML файл диалогов",
        filetypes=["*.xml"]
    )

# Asking for sorting dialogs (uses only when strings.xml is selected)

def ask_sort_choice():
    print("\nНужна ли сортировка реплик по персонажам?")
    print("y - Да (по умолчанию)")
    print("n - Нет")
    while True:
        choice = input("Введите y или n [y]: ").strip().lower()
        if choice == "":
            return "y"
        if choice in ("y", "n"):
            return choice
        print("Некорректный ввод, попробуйте снова.")

# If script encounters a error he is asking for retry first

def ask_retry():
    while True:
        choice = input("\nХотите выбрать другой файл? y/n [n]: ").strip().lower()
        if choice in ("", "n"):
            return False
        if choice == "y":
            return True
        print("Некорректный ввод, попробуйте снова.")

# Waits for user input before exiting.

def wait_and_exit():
    input("\nНажмите Enter для выхода...")
    exit(1)

# Saving output file

def save_output(output_data, xml_path):
    output_path = os.path.splitext(xml_path)[0] + "_dialogues.json"

    if os.path.exists(output_path):
        print(f"\nФайл уже существует:\n{output_path}")
        while True:
            choice = input("Перезаписать? y/n [n]: ").strip().lower()
            if choice in ("", "n"):
                print("Сохранение отменено.")
                return None
            if choice == "y":
                break
            print("Некорректный ввод, попробуйте снова.")

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
    except OSError as e:
        logging.error(f"Не удалось сохранить файл: {e}")
        return None

    return output_path

# Printing stats to CLI

def print_stats(stats):
    print("\nСтатистика по персонажам:")
    for name, s in sorted(stats.items()):
        print(
            f"  - {name}: "
            f"реплик = {s['replicas']}, "
            f"слов = {s['words']}, "
            f"символов = {s['characters']}"
        )

# Main function

def main():
    print("Dialogs parser to JSON by stakanyash")
    print("Version 2.0\n")

    while True:
        print("Выберите XML файл диалогов.")
        xml_file = select_file()

        if not xml_file:
            print("Файл не выбран.")
            if ask_retry():
                continue
            wait_and_exit()

        file_type = detect_file_type(xml_file)
        if file_type is None:
            logging.error("Неизвестный или неподдерживаемый формат файла.")
            if ask_retry():
                continue
            wait_and_exit()

        if file_type == "strings":
            logging.info("Определён формат: strings.xml")
            data = extract_strings_dialogues(xml_file)
        else:
            logging.info("Определён формат: dialogsglobal.xml")
            data = extract_dialogs_global(xml_file)

        if data is None:
            if ask_retry():
                continue
            wait_and_exit()

        stats = calculate_stats(data, file_type)

        # We need sorting only for strings.
        if file_type == "strings":
            choice = ask_sort_choice()
            if choice == "y":
                output_dialogues = dict(data)
            else:
                output_dialogues = [
                    {"name": name, "text": text}
                    for name, replicas in data.items()
                    for text in replicas
                ]
        else:
            output_dialogues = data

        output_data = {
            "dialogues": output_dialogues,
            "statistics": stats
        }

        output_path = save_output(output_data, xml_file)
        if output_path is None:
            if ask_retry():
                continue
            wait_and_exit()

        print(f"\nГотово! Файл сохранён:\n{output_path}")
        print_stats(stats)
        wait_and_exit()

if __name__ == "__main__":
    main()