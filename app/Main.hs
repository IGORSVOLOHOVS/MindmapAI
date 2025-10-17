#!/usr/bin/env stack
{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE LambdaCase #-}

import           Configuration.Dotenv             (loadFile, defaultConfig)
import           Control.Monad                    (void)
import           Control.Monad.IO.Class           (liftIO)
import qualified Data.ByteString                  as BS
import           Data.Default.Class               (def)
import           Data.Text                        (Text)
import qualified Data.Text                        as T
import qualified Data.Text.IO                     as T.IO
import           System.Directory                 (findExecutable, removeFile)
import           System.Environment               (getEnv)
import           System.Exit                      (ExitCode (..))
import           System.FilePath                  (replaceExtension)
import           System.IO                        (hClose)
import           System.IO.Temp                   (withSystemTempFile)
import           System.Process                   (readProcessWithExitCode)
import           Telegram.Bot.API
import           Telegram.Bot.API.Types
import           Telegram.Bot.Simple
import           Telegram.Bot.Simple.UpdateParser (updateMessageText)

-- | A list of irrelevant phrases to filter out from brainstorm sessions.
irrelevantPhrases :: [Text]
irrelevantPhrases = ["хорошо поел"]

-- | Checks if a given text contains any of the irrelevant phrases.
isIrrelevant :: Text -> Bool
isIrrelevant txt = any (`T.isInfixOf` T.strip txt) irrelevantPhrases

-- | Generates a short, Mermaid-compatible ID for a task description.
generateTaskId :: Text -> Text
generateTaskId = T.intercalate "_" . take 2 . T.words . T.toLower . T.strip

-- | Creates a task item tuple (ID, Label) from a task description.
createTaskItem :: Text -> (Text, Text)
createTaskItem task = (generateTaskId task, T.strip task)

-- | Formats a single node for the Mermaid diagram.
formatNode :: (Text, Text) -> Text
formatNode (id, label) = 
  let
    open = T.pack ['[', '"', '`']
    close = T.pack ['`', '"', ']']
  in "    " <> id <> open <> label <> close

-- | Formats a single link for the Mermaid diagram.
formatLink :: (Text, Text) -> (Text, Text) -> Text
formatLink (id1, _) (id2, _) = "    " <> id1 <> " --> " <> id2

-- | Builds a Mermaid flowchart string from a list of task descriptions.
buildMermaidGraph :: [Text] -> Text
buildMermaidGraph tasks = 
  let 
    taskItems = map createTaskItem tasks
    header = T.unlines
      [ "---"
      , "config:"
      , "  flowchart:"
      , "    htmlLabels: false"
      , "---"
      , "flowchart LR"
      ]
    nodes = T.unlines $ map formatNode taskItems
    links = T.unlines $ zipWith formatLink taskItems (tail taskItems)
  in header <> nodes <> links

-- | Processes a text message to see if it's a brainstorm session that can be
-- turned into a Mermaid diagram.
processBrainstorm :: Text -> Maybe Text
processBrainstorm txt = 
  let 
    cleanedTxt = T.strip $ T.replace "/plan" "" txt
    tasks = map T.strip $ T.splitOn "," cleanedTxt
    relevantTasks = filter (not . T.null) $ filter (not . isIrrelevant) tasks
  in 
    if length relevantTasks > 1 
    then Just (buildMermaidGraph relevantTasks)
    else Nothing

data BotState = BotState { mmdcExecutable :: Maybe FilePath }

data Action
  = NoAction
  | Reply ChatId Text
  deriving (Show)

geminiModel :: String
geminiModel = "gemini-2.5-flash"

bot :: BotApp BotState Action
bot = BotApp
  { botInitialModel = BotState { mmdcExecutable = Nothing }
  , botAction = \update _model -> 
      case (updateMessageText update, updateChatId update) of
        (Just txt, Just chatId) -> Just (Reply chatId txt)
        _                       -> Nothing

  , botHandler = \action model -> case action of
      NoAction -> pure model
      Reply chatId txt -> model <# do
        case processBrainstorm txt of 
          Just mermaidGraph -> 
            case mmdcExecutable model of 
              Just mmdc -> replyWithMermaidImage chatId mmdc mermaidGraph
              Nothing   -> do
                void $ reply (toReplyMessage "Диаграмма (mmdc не найден, отправляю текстом):")
                void $ reply (toReplyMessage ("```mermaid\n" <> mermaidGraph <> "\n```"))
          Nothing -> do
            void $ reply (toReplyMessage "🧠 Думаю над вашим запросом...")
            (exitCode, stdout, stderr) <- liftIO $ callGeminiCLI (T.unpack txt)
            let replyTextMsg = case exitCode of 
                  ExitSuccess   -> T.pack stdout
                  ExitFailure _ -> T.pack $ "Произошла ошибка: " ++ stderr
            void $ reply (toReplyMessage replyTextMsg)
  , botJobs = []
  }

replyWithMermaidImage :: ChatId -> FilePath -> Text -> BotM ()
replyWithMermaidImage chatId mmdcPath mermaidTxt = do
  void $ reply (toReplyMessage "Генерирую диаграмму...")
  liftIO (withSystemTempFile "diagram.mmd" $ \mmdPath h -> do
    T.IO.hPutStr h mermaidTxt
    hClose h
    let pngPath = replaceExtension mmdPath ".png"
    (exitCode, stdout, stderr) <- readProcessWithExitCode mmdcPath ["-i", mmdPath, "-o", pngPath, "-b", "transparent"] ""
    case exitCode of 
      ExitSuccess -> pure (Right pngPath)
      ExitFailure _ -> pure (Left (stdout ++ stderr))
    ) >>= \case
      Left err -> void $ reply (toReplyMessage (T.pack $ "Ошибка генерации PNG: " ++ err))
      Right pngPath -> do
        let photo = SendPhotoRequest
              { sendPhotoChatId = SomeChatId chatId
              , sendPhotoPhoto = PhotoFile pngPath "image/png"
              , sendPhotoCaption = Nothing
              , sendPhotoDisableNotification = Nothing
              , sendPhotoReplyToMessageId = Nothing
              , sendPhotoReplyMarkup = Nothing
              }
        _ <- liftClientM $ sendPhoto photo
        liftIO $ removeFile pngPath

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

      putStrLn "1.1. Проверка наличия `mmdc` (Mermaid CLI)..."
      mmdcPath <- findExecutable "mmdc"
      case mmdcPath of 
        Nothing -> putStrLn "[ПРЕДУПРЕЖДЕНИЕ] Утилита `mmdc` не найдена. Диаграммы будут отправляться как текст. Установите ее: npm install -g @mermaid-js/mermaid-cli"
        Just mmdc -> putStrLn $ "   `mmdc` найден: " ++ mmdc

      putStrLn "2. Получение токена Telegram..."
      putStrLn "   (Используется переменная TELEGRAM_BOT_TOKEN из файла .env)"
      token <- Token . T.pack <$> getEnv "TELEGRAM_BOT_TOKEN"

      let model = BotState { mmdcExecutable = mmdcPath }

      env <- defaultTelegramClientEnv token
      putStrLn "3. Запуск бота... (Нажмите Ctrl+C для остановки)"
      startBot_ (bot { botInitialModel = model }) env
