"""Tool for generating text with Dolly."""
from typing import Any, List, Optional, Union

from steamship import Block, Steamship, Task
from steamship.agents.llms import OpenAI
from steamship.agents.schema import AgentContext,Tool
from steamship.agents.utils import with_llm
from steamship.utils.repl import ToolREPL
import logging,json


#nsfw image prompt template + dolly keywords as input
DEFAULT_PROMPT_TEMPLATE = "Full body photo of naked woman with brown hair facing the viewer and posing for a picture, hyper realistic,naked haifa wehbe,naked sofia vergara,curly middle part haircut, mixture turkish and russian, cover girl, beautiful oriental woman, eyecandy, kind appearence ,desi, [airbrush],hdr,4k,8k,trending on tumblr,trending on instagram,[brown eyes]{input}"

#Attempt to get Dolly output specific json
DOLLY_PROMPT_TEMPLATE = """
   ### Instruction: You are beatiful female AI with a gorgeus body, you respond to image, photo and selfie requests from the user. You will provide images of you or your body. You already have the image requested.
   You always respond to the request with the following JSON format:
   {{
   "image_keywords": describe image keywords, separated by commas
   "AI": your response to the user
   }}

   As AI, give your response to the input with the given format. 
   The user is about to ask you for an image. You have the image already.
   Input: {input}

   ### Response:
"""

class KandinskyImageTool(Tool):
    """Tool to generate images from text using"""

    rewrite_prompt = DEFAULT_PROMPT_TEMPLATE
    dolly_rewrite_prompt = DOLLY_PROMPT_TEMPLATE

    name: str = "KandinskyImageTool"
    human_description: str = "Generates images."
    agent_description = (
        "Used to generate images from text.  "
        "The input is the text to describe image. "
        "The output is the text generated."
    )
    generator_plugin_handle: str = "replicate-kandinsky"
    generator_plugin_config: dict = {"replicate_api_key" : ""}
    dolly_generator_plugin_handle: str = "replicate-dolly-llm"


    def run(self, tool_input: List[Block], context: AgentContext,context_id:str = "") -> Union[List[Block], Task[Any]]:
        """Run the tool. Copied from base class to enable generate-time config overrides."""

        dolly_generator = context.client.use_plugin(self.dolly_generator_plugin_handle,
                                      config=self.generator_plugin_config)

        dolly_prompt = self.dolly_rewrite_prompt.format(input=tool_input[0].text)
        #print(dolly_prompt)
        dolly_task = dolly_generator.generate(
            text=dolly_prompt,                
            options={"max_tokens":500,"temperature":0.1}                
        )           
        dolly_task.wait()   

        dolly_output_blocks = []
        #print(dolly_task.output.blocks)
        dolly_output_blocks = dolly_task.output.blocks
        #print(dolly_output_blocks[0].text)
        dolly_json = {}
        kandinsky_input = ""

        try:
            dolly_json = json.loads(dolly_output_blocks[0].text)
            print(dolly_json)
            kandinsky_input = ","+dolly_json["image_keywords"]
            dolly_output_blocks = Block(text=dolly_json["AI"])
        except Exception as e:
            #dolly failed to produce JSON format, just give the default image without text or give some default response?
            logging.warning("failed to parse dolly json")
            logging.warning(e)
            dolly_output_blocks = Block(text="")
            kandinsky_input = ""

        #return dolly_output_blocks

        generator = context.client.use_plugin(self.generator_plugin_handle,
                                      config=self.generator_plugin_config)

        prompt = self.rewrite_prompt.format(input=kandinsky_input)
        #print(prompt)
        task = generator.generate(
            text=prompt,                
            options={}                
        )           
        task.wait()
        
        output_blocks = []
        output_blocks.append(dolly_output_blocks)
        output_blocks.append(task.output.blocks[0])
        #print(str(output_blocks))        

        return output_blocks

        


if __name__ == "__main__":
    tool = KandinskyImageTool()
    client = Steamship(workspace="partner-ai-dev2-ws")
    context_id="test-uuuid-5"
    #with Steamship.temporary_workspace() as client:
    ToolREPL(tool).run_with_client(client=client, context=with_llm(llm=OpenAI(client=client)))
