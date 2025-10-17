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

-- | A list of irrelevant phrases to filter out from brainstorm sessions.
irrelevantPhrases :: [Text]
irrelevantPhrases = ["хорошо поел"]

-- | Checks if a given text contains any of the irrelevant phrases.
isIrrelevant :: Text -> Bool
isIrrelevant txt = any (`T.isInfixOf` T.strip txt) irrelevantPhrases

-- | Generates a short, Mermaid-compatible ID for a task description.
-- Example: "исправление функции" -> "исправление_функции"
generateTaskId :: Text -> Text
generateTaskId = T.intercalate "_" . take 2 . T.words . T.toLower . T.strip

-- | Builds a Mermaid flowchart string from a list of task descriptions.
buildMermaidGraph :: [Text] -> Text
buildMermaidGraph tasks =
  let
    -- Create (ID, Label) pairs for each task.
    taskItems = map (\task -> (generateTaskId task, T.strip task)) tasks
    -- Mermaid diagram header.
    header = T.unlines
      [ "```mermaid"
      , "---"
      , "config:"
      , "  flowchart:"
      , "    htmlLabels: false"
      , "---"
      , "flowchart LR"
      ]
    -- Define nodes for the graph.
    nodes = T.unlines $ map (\(id, label) -> "    " <> id <> "[\"`" <> label <> "`\"]") taskItems
    -- Define links between nodes.
    links = T.unlines $ zipWith (\(id1, _) (id2, _) -> "    " <> id1 <> " --> " <> id2) taskItems (tail taskItems)
    footer = "```"
  in header <> nodes <> links <> footer

-- | Processes a text message to see if it's a brainstorm session that can be
-- turned into a Mermaid diagram.
processBrainstorm :: Text -> Maybe Text
processBrainstorm txt =
  -- Split the message by commas to get individual tasks.
  let tasks = map T.strip $ T.splitOn "," txt
      -- Filter out any irrelevant tasks.
      relevantTasks = filter (not . isIrrelevant) tasks
  in
    -- Only generate a diagram if there are two or more relevant tasks.
    if length relevantTasks > 1
    then Just (buildMermaidGraph relevantTasks)
    else Nothing

data Action
  = NoAction
  | Reply ChatId Text
  deriving (Show)

geminiModel :: String
geminiModel = "gemini-2.5-flash"

bot :: BotApp () Action
bot = BotApp
  {
    botInitialModel = ()
  , botAction = \update _model ->
      case (updateMessageText update, updateChatId update) of
        (Just txt, Just chatId) -> Just (Reply chatId txt)
        _                       -> Nothing

  , botHandler = \action model -> case action of
      NoAction -> pure model
      Reply chatId txt -> model <# do
        -- Try to process the message as a brainstorm session first.
        case processBrainstorm txt of
          -- If it's a brainstorm, send the generated Mermaid diagram.
          Just mermaidGraph -> do
            void $ reply (toReplyMessage "Создал для вас диаграмму:")
            void $ reply (toReplyMessage mermaidGraph)
          -- Otherwise, fall back to the default Gemini AI handler.
          Nothing -> do
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
