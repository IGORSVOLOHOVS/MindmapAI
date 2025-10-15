{-# LANGUAGE OverloadedStrings #-}

import           Control.Monad          (void)
import           Data.Maybe             (fromMaybe)
import           Data.Text              (Text)
import qualified Data.Text              as T
import           System.Directory       (findExecutable)
import           System.Environment     (getEnv)
-- ДОБАВЛЯЕМ НОВЫЙ ИМПОРТ
import           System.Environment.DotEnv (loadFile, defaultConfig)
import           System.Process         (readProcessWithExitCode)
import           Telegram.Bot.API
import           Telegram.Bot.Simple
import           Telegram.Bot.Simple.UpdateParser (updateMessageText)

type Model = ()
data Action = NoAction | Reply Text

geminiModel :: String
geminiModel = "gemini-2.5-flash"

bot :: BotApp Model Action
bot = BotApp
  { botInitialModel = ()
  , botAction = \update _model ->
      case updateMessageText update of
        Nothing  -> NoAction
        Just txt -> Reply txt
  , botHandler = \action msg -> case action of
      NoAction -> return ()
      Reply txt -> do
        let chatId = updateChatId msg
        void $ sendChatMessage chatId "🧠 Думаю над вашим запросом..."
        (exitCode, stdout, stderr) <- liftIO $ callGeminiCLI (T.unpack txt)
        let replyText = case exitCode of
              ExitSuccess -> T.pack stdout
              ExitFailure _ -> T.pack $ "Произошла ошибка: " ++ stderr
        void $ sendChatMessage chatId replyText
  , botJobs = []
  }

callGeminiCLI :: String -> IO (ExitCode, String, String)
callGeminiCLI prompt =
  readProcessWithExitCode "gemini" ["-m", geminiModel, "-p", prompt] ""

sendChatMessage :: ChatId -> Text -> BotM ()
sendChatMessage chatId text = void $ runTG $ sendMessage (sendMessageRequest chatId text)

main :: IO ()
main = do
  putStrLn "--- Запуск Haskell Gemini AI Bot ---"
  
  -- 0. Загружаем переменные из .env файла
  -- Это нужно сделать до того, как мы попытаемся их прочитать
  putStrLn "0. Загрузка переменных из файла .env..."
  void $ loadFile defaultConfig

  -- 1. Проверяем, доступна ли утилита 'gemini'
  putStrLn "1. Проверка наличия `gemini-cli`..."
  geminiPath <- findExecutable "gemini"
  case geminiPath of
    Nothing ->
      putStrLn "[ОШИБКА] Утилита `gemini` не найдена в вашем PATH. Установите ее: npm install -g @google/gemini-cli@latest"
    Just path -> do
      putStrLn $ "   `gemini` найден: " ++ path

      -- 2. Получаем токен (теперь он будет взят из .env)
      putStrLn "2. Получение токена Telegram..."
      putStrLn "   (Используется переменная TELEGRAM_BOT_TOKEN из файла .env)"
      token <- Token . T.pack <$> getEnv "TELEGRAM_BOT_TOKEN"
      
      -- 3. Запускаем бота
      env <- defaultTelegramClientEnv token
      putStrLn "3. Запуск бота... (Нажмите Ctrl+C для остановки)"
      startBot_ bot env