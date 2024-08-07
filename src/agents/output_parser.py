import logging
import re
from typing import Dict, List, Optional
from tools.active_companion import *  #upm package(steamship)
from steamship import Block, Steamship  #upm package(steamship)
from steamship.agents.schema import Action, AgentContext, FinishAction, OutputParser, Tool  #upm package(steamship)
from tools.selfie_tool_getimgai import SelfieTool  #upm package(steamship)
from tools.selfie_tool_fal_ai import SelfieToolFalAi  #upm package(steamship)
import json
from typing import List, Optional, Union


class ReACTOutputParser(OutputParser):
    'Parse LLM output expecting structure matching ReACTAgent default prompt'
    tools_lookup_dict: Optional[Dict[str, Tool]] = None
    gen_image = False

    def __init__(self, **kwargs):
        ReACTOutputParser.tools_lookup_dict = {
            tool.name: tool
            for tool in kwargs.pop("tools", [])
        }
        super().__init__(**kwargs)

    def emit(self, output: Union[str, Block, List[Block]],
             context: AgentContext):
        """Emits a message to the user."""
        if isinstance(output, str):
            output = [Block(text=output)]
        elif isinstance(output, Block):
            output = [output]
        for func in context.emit_funcs:
            logging.info(
                f"Emitting via function '{func.__name__}' for context: {context.id}"
            )
            func(output, context.metadata)

    def parse(self, response: str, response_json: Dict,
              context: AgentContext) -> Action:
        current_name = NAME
        meta_name = context.metadata.get("instruction", {}).get("name")
        if meta_name is not None:
            current_name = meta_name
        text = response
        run_tool = None
        run_tool_input = None

        if response_json.get("image", None):
            run_tool_input = response_json.get("image", "")
            #logging.warning(f"run_tool_input: {run_tool_input}")
        
        # Updated regex to match the new directive pattern
        image_action = re.findall(r'<image>\s*\[(.+?)\]\s*</image>',
              text,
              flags=re.IGNORECASE | re.DOTALL)
        if image_action:
            function_call = True
            #logging.warning("image_action: " + str(image_action))
            run_tool = "selfie_tool"
            # Now correctly accessing the first group from the first match
            run_tool_input = [image_action[0]]  
            #logging.warning(f"run_tool_input: {run_tool_input}")
            text = re.sub(r'<image>\[(.+?)\]</image>', '', text, flags=re.IGNORECASE).lstrip().rstrip()
            text = re.sub(r'\[(.+?)\]', '', text, flags=re.IGNORECASE).lstrip().rstrip()
        

        current_model = ""            
        meta_model = context.metadata.get("instruction", {}).get("model")
        if meta_model is not None:
            current_model = meta_model


        text = text.replace(f"**{current_name}:**", "").strip()
        text = text.replace(f"{current_name}:", "").strip()
        
        text = text.replace("### Response:", "").strip()
        text = text.replace('<|im_sep|>', "")
        text = text.replace('<|im_start|>', "")
        text = text.replace('</s>', "")
        text = text.replace(f'As {current_name}, ', "")

        text = re.sub(r'\`', '', text, flags=re.DOTALL | re.IGNORECASE)        
        if len(text) > 600:
            # Updated to strip the text to the last . ? ! if too long
            m = re.search(r'([.!?*"])[^.!?*"]*$', text)
            if m:
                text = text[:m.start()+1]
            
        if text.count('"') == 2:
            text = text.lstrip('"').rstrip('"')
        if text.count('"') == 1:
            text = text.replace('"', "",1)
        
        text = text.replace("[]","",1)
        text = text.replace("\n\n.","")
        text = text.split("#")[0]
        text = text.split("![Keywords:")[0]
        text = text.split("[Image:")[0]
        text = text.split("[*think*:")[0]
        text = text.rstrip().lstrip()

        # Add check if no toolname is defined, but text contains regex keywords, run the tool anyway
        #pattern = r"(\bhere\b|\btakes\b|\bsends\b|\bsnaps\b).*?(?:picture|photo|image|selfie|nude|pic|peek|snapshot)"
        #if run_tool is None and re.search(pattern, text, re.IGNORECASE):
        #    #logging.warning("No toolname defined, but text contains regex keywords, run the tool anyway")
        #    run_tool = "selfie_tool"
        #    run_tool_input = [text]
            
        return FinishAction(output=ReACTOutputParser._blocks_from_text(
            self, context.client, text, run_tool, run_tool_input, context),
                            context=context)

    @staticmethod
    def _blocks_from_text(self, client: Steamship, text: str, tool_name: str,
                          tool_input: List[str],
                          context: AgentContext) -> List[Block]:
        current_name = NAME
        meta_name = context.metadata.get("instruction", {}).get("name")
        if meta_name is not None:
            current_name = meta_name
        result_blocks: List[Block] = []
        block_found = 0
        if text:
            #self.emit(text, context)
            result_blocks.append(Block(text=text))

        saved_block = context.metadata.get("blocks", {}).get("image")
        if saved_block is not None:
            result_blocks.append(Block.get(client, _id=saved_block))
            context.metadata['blocks'] = None
        else:
            create_images = context.metadata.get("instruction",
                                                 {}).get("create_images")
            get_img_ai_models = [
                "realistic-vision-v3", "dark-sushi-mix-v2-25",
                "absolute-reality-v1-8-1", "van-gogh-diffusion",
                "neverending-dream", "mo-di-diffusion", "synthwave-punk-v2",
                "dream-shaper-v8","arcane-diffusion"
            ]
            pattern = r"(\bhere\b|\btake\b|\bsends\b|\bhere\'s\b).*?(?:picture|photo|image|selfie|nude|pic|peek)"
            sending_image = re.search(pattern,
                      text,
                      re.IGNORECASE)
            
            if create_images == "true":
                if tool_name:
                    image_model = context.metadata.get("instruction",
                                                       {}).get("image_model")
                    if image_model is not None and image_model not in get_img_ai_models:
                        tool_name = tool_name + "_fal_ai"  #change to fal.ai tool

                    selfie_tool = ReACTOutputParser.tools_lookup_dict.get(
                        tool_name, None)
                    if selfie_tool and tool_input is not None:
                        image_block = selfie_tool.run(
                            [Block(text=','.join(tool_input))], context,stream=True)
                        if image_block:
                            result_blocks.extend(image_block)
                            #context.chat_history.append_user_message(
                            #    "I received the image!"
                            #)                
        return result_blocks