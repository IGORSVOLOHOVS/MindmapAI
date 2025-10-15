# Проверяем, установлен ли gemini
if ! command -v gemini &> /dev/null
then
    echo "gemini-cli не найден. Устанавливаю..."
    # Устанавливаем, если его нет (может потребоваться sudo)
    npm install -g @google/gemini-cli@latest

    # Проверяем, установлен ли gemini после установки
    if command -v gemini &> /dev/null
    then
        echo "gemini-cli установлено."
    else
        echo "Ошибка установки gemini-cli."
        exit 1
    fi
fi
else
    echo "gemini-cli уже установлен."
fi