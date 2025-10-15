{-# LANGUAGE OverloadedStrings #-}

import           Configuration.Dotenv             (loadFile, defaultConfig)
import           Control.Monad                    (void)
import           Control.Monad.IO.Class           (liftIO)
import           Data.Text                        (Text)
import qualified Data.Text                        as T
import           System.Directory                 (findExecutable)
import           System.Environment               (getEnv)
import           System.Exit                      (ExitCode (..))
import           System.Process                   (readProcessWithExitCode)
import           Telegram.Bot.API
import           Telegram.Bot.Simple
import           Telegram.Bot.Simple.UpdateParser (updateMessageText)

data Action
  = NoAction
  | Reply ChatId Text
  deriving (Show)

geminiModel :: String
geminiModel = "gemini-2.5-flash"

bot :: BotApp () Action
bot = BotApp
  { botInitialModel = ()
  , botAction = \update _model ->
      case (updateMessageText update, updateChatId update) of
        (Just txt, Just chatId) -> Just (Reply chatId txt)
        _                       -> Nothing

  , botHandler = \action model -> case action of
      NoAction -> pure model
      Reply chatId txt -> model <# do
        void $ reply (toReplyMessage "🧠 Думаю над вашим запросом...")

        (exitCode, stdout, stderr) <- liftIO $ callGeminiCLI (T.unpack txt)

        let replyTextMsg = case exitCode of
              ExitSuccess   -> T.pack stdout
              ExitFailure _ -> T.pack $ "Произошла ошибка: " ++ stderr

        void $ reply (toReplyMessage replyTextMsg)
  , botJobs = []
  }

callGeminiCLI :: String -> IO (ExitCode, String, String)
callGeminiCLI prompt =
  readProcessWithExitCode "gemini" ["-m", geminiModel, "-p", prompt] ""

main :: IO ()
main = do
  putStrLn "--- Запуск Haskell Gemini AI Bot ---"

  putStrLn "0. Загрузка переменных из файла .env..."
  void $ loadFile defaultConfig

  putStrLn "1. Проверка наличия `gemini-cli`..."
  geminiPath <- findExecutable "gemini"
  case geminiPath of
    Nothing ->
      putStrLn "[ОШИБКА] Утилита `gemini` не найдена в вашем PATH. Установите ее: npm install -g @google/gemini-cli@latest"
    Just path -> do
      putStrLn $ "   `gemini` найден: " ++ path

      putStrLn "2. Получение токена Telegram..."
      putStrLn "   (Используется переменная TELEGRAM_BOT_TOKEN из файла .env)"
      token <- Token . T.pack <$> getEnv "TELEGRAM_BOT_TOKEN"

      env <- defaultTelegramClientEnv token
      putStrLn "3. Запуск бота... (Нажмите Ctrl+C для остановки)"
      startBot_ bot env