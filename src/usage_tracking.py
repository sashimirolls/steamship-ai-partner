from typing import Optional,List
import time
from pydantic import BaseModel
from steamship import Steamship,Block #upm package(steamship)
from tools.kv_store import KeyValueStore #upm package(steamship)
from steamship.utils.context_length import token_length #upm package(steamship)
import logging


class UsageEntry(BaseModel):
    message_count: int = 0
    message_limit: int = 0
    usd_balance: float = 0
    indexed:int = 0
    level:int = 1
    previous_level = 0
    mood:str = "normal"
    engagement:str = ""
    previous_level

    


class UsageTracker:
    kv_store: KeyValueStore
    gpt_price_per_thousand_tokens = 1           #Calculate price for GPT, default 0.18c/1000 tokens 
    elevenlabs_price_per_thousand_chars = 1        #Calculate price based on generated voice, default price 0.30c/1000 chars
    chars_per_minute = 1010
    timing = True
    
    def __init__(self, client: Steamship, n_free_messages: Optional[int] = 0,usd_balance: Optional[float] = 0,level: Optional[int] = 1,mood: Optional[str] = "neutral",context_id:str="default"):
        self.kv_store = KeyValueStore(client, store_identifier=f"usage_tracking_{context_id}")
        self.n_free_messages = n_free_messages
        self.usd_balance = usd_balance
        self.level = level
        self.mood = mood

    def set_kv_store(self,client: Steamship,storage_identifier="default"):
        self.kv_store = KeyValueStore(client, store_identifier=storage_identifier)
                                      
    def increase_token_count(self, blocks: [Block], chat_id: str,use_voice:bool ):
        usage_entry = self.get_usage(chat_id)
        #if free message limit reached
        if usage_entry.message_count >= usage_entry.message_limit:
            chars_used = 0 
            tokens_used = 0       
            for token_block in blocks:
                if token_block is not None and token_block.text:
                    num_tokens = token_length(token_block,tiktoken_encoder="cl100k_base") #gpt3/4 tokenizer
                    tokens_used += num_tokens
                    chars_used += len(token_block.text)                                    
            
            usage_entry.usd_balance -= self.calculate_cost(num_tokens=tokens_used,num_chars=chars_used,use_voice=use_voice)
            if usage_entry.usd_balance < 0:
                usage_entry.usd_balance = 0
            self._set_usage(chat_id, usage_entry)
            return tokens_used
    
    def calculate_cost(self, num_tokens:int,num_chars:int,use_voice:bool):
        #calculate tokens and voice cost in USD
        cost_per_token = self.gpt_price_per_thousand_tokens / 1000
        token_cost = num_tokens * cost_per_token
        voice_price = (num_chars / self.chars_per_minute) * self.elevenlabs_price_per_thousand_chars
        #logging.info("used balance in USD: "+str(token_cost+voice_price))
        if use_voice:
            return voice_price   #return voice_price+token_cost for both
        else:
            return token_cost
    
    def get_available_words(self,chat_id):
        #get available words from balance
        usage_entry = self.get_usage(chat_id)
        cost_per_char = self.elevenlabs_price_per_thousand_chars / self.chars_per_minute
        chars_left = int(usage_entry.usd_balance / cost_per_char)
        tokens = chars_left / 4
        words = tokens * 0.75
        return int(words)
            
    def get_balance(self,chat_id):
        #get rounded balance
        usage_entry = self.get_usage(chat_id)      
        if usage_entry.usd_balance < 0:
            usage_entry.usd_balance = 0
        #logging.info(str(usage_entry.usd_balance))
        return round(usage_entry.usd_balance,2)

    def get_usage(self, chat_id) -> UsageEntry:
        if self.timing:
            start_time = time.time()
        if not self.exists(chat_id):
            self.add_user(chat_id)
        usage_entry = self.kv_store.get(chat_id)
        end_time = time.time() - start_time
        if self.timing and end_time > 0.1:
            logging.warning("Usage tracking get duration " + str(end_time))
        return UsageEntry.parse_obj(usage_entry)

    def set_level(self, chat_id, level):
        usage_entry = self.get_usage(chat_id)
        usage_entry.level = level
        self._set_usage(chat_id, usage_entry)

    def get_level(self, chat_id):
        usage_data = self.get_usage(chat_id)
        return usage_data.level
        
    def set_previous_level(self, chat_id, level):
        usage_entry = self.get_usage(chat_id)
        usage_entry.previous_level = level
        self._set_usage(chat_id, usage_entry)

    def get_previous_level(self, chat_id):
        usage_data = self.get_usage(chat_id)
        return usage_data.previous_level
        
    def get_engagement(self,chat_id):
        usage_data = self.get_usage(chat_id)
        return usage_data.engagement

    def set_engagement(self, chat_id, engagement):
        usage_data = self.get_usage(chat_id)
        usage_data.engagement = engagement
        self._set_usage(chat_id, usage_data)
        
    def set_mood(self, chat_id, mood):
        usage_entry = self.get_usage(chat_id)
        usage_entry.mood = mood
        self._set_usage(chat_id, usage_entry)

    def get_mood(self, chat_id):
        usage_entry = self.get_usage(chat_id)
        return usage_entry.mood
        
    def set_index_status(self,chat_id):
        usage_entry = self.get_usage(chat_id)   
        usage_entry.indexed = 1
        self._set_usage(chat_id, usage_entry)    
    
    def get_index_status(self,chat_id):      
         usage_entry = self.get_usage(chat_id)
         return usage_entry.indexed

    def get_usage_entry(self, chat_id):
        return self.get_usage(chat_id)

    def set_usage_entry(self, chat_id, usage_entry):
        self._set_usage(chat_id, usage_entry)
    
    def _set_usage(self, chat_id, usage: UsageEntry) -> None:
        if self.timing:
            start_time = time.time()
        self.kv_store.set(chat_id, usage.dict())
        end_time = time.time() - start_time
        if self.timing and end_time > 0.1:            
            logging.warning("Usage tracking set duration " + str(end_time))

    def usage_exceeded(self, chat_id: str):
        usage_entry = self.kv_store.get(chat_id)
        if usage_entry["message_count"] > usage_entry["message_limit"] and self.get_balance(chat_id=chat_id) <= 0:
            return True
        else:
            return False


    def add_user(self, chat_id: str):
        self._set_usage(chat_id, UsageEntry(message_limit=self.n_free_messages,usd_balance=self.usd_balance))

    def exists(self, chat_id: str):
        return self.kv_store.get(chat_id) is not None

    def increase_message_count(self, chat_id: str, n_messages: Optional[int] = 1):
        usage_entry = self.get_usage(chat_id)
        usage_entry.message_count += n_messages
        self._set_usage(chat_id, usage_entry)
        return usage_entry.message_count

    def increase_message_limit(self, chat_id: str, n_messages: int):
        usage_entry = self.get_usage(chat_id)
        usage_entry.message_limit += n_messages
        self._set_usage(chat_id, usage_entry)

    def increase_usd_balance(self, chat_id: str, deposit: float):
        usage_entry = self.get_usage(chat_id)
        usage_entry.usd_balance += deposit
        self._set_usage(chat_id, usage_entry)        
