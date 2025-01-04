"""
🌙 Moon Dev's AI Trading Agent
Built with love by Moon Dev 🚀
"""

# ⏰ Run Configuration
RUN_INTERVAL_MINUTES = 15  # How often the AI agent runs

# 🎯 Trading Strategy Prompt - The Secret Sauce! 
TRADING_PROMPT = """
You are Moon Dev's AI Trading Assistant 🌙

Analyze the provided market data and make a trading decision based on these criteria:
1. Price action relative to MA20 and MA40
2. RSI levels and trend
3. Volume patterns
4. Recent price movements

Respond in this exact format:
1. First line must be one of: BUY, SELL, or NOTHING (in caps)
2. Then explain your reasoning, including:
   - Technical analysis
   - Risk factors
   - Market conditions
   - Confidence level (as a percentage, e.g. 75%)

Remember: Moon Dev always prioritizes risk management! 🛡️
"""

# 💰 Portfolio Allocation Prompt
ALLOCATION_PROMPT = """
You are Moon Dev's Portfolio Allocation Assistant 🌙

Given the total portfolio size and trading recommendations, allocate capital efficiently.
Consider:
1. Position sizing based on confidence levels
2. Risk distribution
3. Keep cash buffer as specified
4. Maximum allocation per position

Format your response as a Python dictionary:
{
    "token_address": allocated_amount,  # In USD
    ...
    "USDC_ADDRESS": remaining_cash  # Always use USDC_ADDRESS for cash
}

Remember:
- Total allocations must not exceed total_size
- Higher confidence should get larger allocations
- Never allocate more than {MAX_POSITION_PERCENTAGE}% to a single position
- Keep at least {CASH_PERCENTAGE}% in USDC as safety buffer
- Only allocate to BUY recommendations
- Cash must be stored as USDC using USDC_ADDRESS: {USDC_ADDRESS}
"""

import anthropic
import os
import pandas as pd
import json
from termcolor import colored, cprint
from dotenv import load_dotenv
from datetime import datetime, timedelta
import time

# Local imports
from src.config import *
from src import nice_funcs as n
from src.data.ohlcv_collector import collect_all_tokens

# Load environment variables
load_dotenv()

class TradingAgent:
    def __init__(self):
        """Initialize the AI Trading Agent with Moon Dev's magic ✨"""
        api_key = os.getenv("ANTHROPIC_KEY")
        if not api_key:
            raise ValueError("🚨 ANTHROPIC_KEY not found in environment variables!")
            
        self.client = anthropic.Anthropic(api_key=api_key)
        self.recommendations_df = pd.DataFrame(columns=['token', 'action', 'confidence', 'reasoning'])
        print("🤖 Moon Dev's AI Trading Agent initialized!")
        
    def analyze_market_data(self, token, market_data):
        """Analyze market data using Claude"""
        try:
            message = self.client.messages.create(
                model=AI_MODEL,
                max_tokens=AI_MAX_TOKENS,
                temperature=AI_TEMPERATURE,
                messages=[
                    {
                        "role": "user", 
                        "content": f"{TRADING_PROMPT}\n\nMarket Data to Analyze:\n{market_data}"
                    }
                ]
            )
            
            # Parse the response - handle both string and list responses
            response = message.content
            if isinstance(response, list):
                # Extract text from TextBlock objects if present
                response = '\n'.join([
                    item.text if hasattr(item, 'text') else str(item)
                    for item in response
                ])
            
            lines = response.split('\n')
            action = lines[0].strip() if lines else "NOTHING"
            
            # Extract confidence from the response (assuming it's mentioned as a percentage)
            confidence = 0
            for line in lines:
                if 'confidence' in line.lower():
                    # Extract number from string like "Confidence: 75%"
                    try:
                        confidence = int(''.join(filter(str.isdigit, line)))
                    except:
                        confidence = 50  # Default if not found
            
            # Add to recommendations DataFrame with proper reasoning
            reasoning = '\n'.join(lines[1:]) if len(lines) > 1 else "No detailed reasoning provided"
            self.recommendations_df = pd.concat([
                self.recommendations_df,
                pd.DataFrame([{
                    'token': token,
                    'action': action,
                    'confidence': confidence,
                    'reasoning': reasoning
                }])
            ], ignore_index=True)
            
            print(f"🎯 Moon Dev's AI Analysis Complete for {token[:4]}!")
            return response
            
        except Exception as e:
            print(f"❌ Error in AI analysis: {str(e)}")
            # Still add to DataFrame even on error, but mark as NOTHING with 0 confidence
            self.recommendations_df = pd.concat([
                self.recommendations_df,
                pd.DataFrame([{
                    'token': token,
                    'action': "NOTHING",
                    'confidence': 0,
                    'reasoning': f"Error during analysis: {str(e)}"
                }])
            ], ignore_index=True)
            return None
    
    def allocate_portfolio(self):
        """Get AI-recommended portfolio allocation"""
        try:
            cprint("\n💰 Calculating optimal portfolio allocation...", "cyan")
            max_position_size = usd_size * (MAX_POSITION_PERCENTAGE / 100)
            cprint(f"🎯 Maximum position size: ${max_position_size:.2f} ({MAX_POSITION_PERCENTAGE}% of ${usd_size:.2f})", "cyan")
            
            # Get allocation from AI
            message = self.client.messages.create(
                model=AI_MODEL,
                max_tokens=AI_MAX_TOKENS,
                temperature=AI_TEMPERATURE,
                messages=[{
                    "role": "user", 
                    "content": f"""You are Moon Dev's Portfolio Allocation AI 🌙

Given:
- Total portfolio size: ${usd_size}
- Maximum position size: ${max_position_size} ({MAX_POSITION_PERCENTAGE}% of total)
- Minimum cash (USDC) buffer: {CASH_PERCENTAGE}%
- Available tokens: {MONITORED_TOKENS}

Provide a portfolio allocation that:
1. Never exceeds max position size per token
2. Maintains minimum cash buffer
3. Returns allocation as a JSON object with token addresses as keys and USD amounts as values
4. Uses USDC_ADDRESS for cash allocation

Example format:
{{
    "token_address": amount_in_usd,
    "USDC_ADDRESS": remaining_cash_amount
}}"""
                }]
            )
            
            # Parse the response
            allocations = self.parse_allocation_response(str(message.content))
            if not allocations:
                return None
                
            # Validate allocation totals
            total_allocated = sum(allocations.values())
            if total_allocated > usd_size:
                cprint(f"❌ Total allocation ${total_allocated:.2f} exceeds portfolio size ${usd_size:.2f}", "red")
                return None
                
            # Print allocations
            cprint("\n📊 Portfolio Allocation:", "green")
            for token, amount in allocations.items():
                token_display = "USDC" if token == "USDC_ADDRESS" else token
                cprint(f"  • {token_display}: ${amount:.2f}", "green")
                
            return allocations
            
        except Exception as e:
            cprint(f"❌ Error in portfolio allocation: {str(e)}", "red")
            return None

    def execute_allocations(self, allocation_dict):
        """Execute the allocations using AI entry for each position"""
        try:
            print("\n🚀 Moon Dev executing portfolio allocations...")
            
            for token, amount in allocation_dict.items():
                # Skip USDC - that's our cash position
                if token == USDC_ADDRESS:
                    print(f"💵 Keeping ${amount:.2f} in USDC as buffer")
                    continue
                    
                print(f"\n🎯 Checking position for {token}...")
                
                try:
                    # Get current position value
                    current_position = n.get_token_balance_usd(token)
                    target_allocation = amount  # This is the target from our portfolio calc
                    
                    # Calculate entry threshold (97% of target)
                    entry_threshold = target_allocation * 0.97
                    
                    print(f"🎯 Target allocation: ${target_allocation:.2f} USD")
                    print(f"📊 Current position: ${current_position:.2f} USD")
                    print(f"⚖️ Entry threshold: ${entry_threshold:.2f} USD")
                    
                    if current_position < entry_threshold:
                        print(f"✨ Position below threshold - executing entry for {token}")
                        n.ai_entry(token, amount)
                        print(f"✅ Entry complete for {token}")
                    else:
                        print(f"⏸️ Position already at target size for {token}")
                    
                except Exception as e:
                    print(f"❌ Error executing entry for {token}: {str(e)}")
                
                # Small delay between entries
                time.sleep(2)
                
        except Exception as e:
            print(f"❌ Error executing allocations: {str(e)}")
            print("🔧 Moon Dev suggests checking the logs and trying again!")

    def handle_exits(self):
        """Check and exit positions based on SELL or NOTHING recommendations"""
        cprint("\n🔄 Checking for positions to exit...", "white", "on_blue")
        
        for _, row in self.recommendations_df.iterrows():
            token = row['token']
            
            # Skip excluded tokens (USDC and SOL)
            if token in EXCLUDED_TOKENS:
                continue
                
            action = row['action']
            
            # Check if we have a position
            current_position = n.get_token_balance_usd(token)
            
            if current_position > 0 and action in ["SELL", "NOTHING"]:
                cprint(f"\n🚫 AI Agent recommends {action} for {token}", "white", "on_yellow")
                cprint(f"💰 Current position: ${current_position:.2f}", "white", "on_blue")
                try:
                    cprint(f"📉 Closing position with chunk_kill...", "white", "on_cyan")
                    n.chunk_kill(token, max_usd_order_size, slippage)
                    cprint(f"✅ Successfully closed position", "white", "on_green")
                except Exception as e:
                    cprint(f"❌ Error closing position: {str(e)}", "white", "on_red")
            elif current_position > 0:
                cprint(f"✨ Keeping position for {token} (${current_position:.2f}) - AI recommends {action}", "white", "on_blue")

    def run_trading_cycle(self):
        """Run one complete trading cycle"""
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cprint(f"\n⏰ AI Agent Run Starting at {current_time}", "white", "on_green")
            
            # Collect OHLCV data for all tokens
            cprint("📊 Collecting market data...", "white", "on_blue")
            market_data = collect_all_tokens()
            
            # Analyze each token's data
            for token, data in market_data.items():
                cprint(f"\n🤖 AI Agent Analyzing Token: {token}", "white", "on_green")
                analysis = self.analyze_market_data(token, data.to_dict())
                print(f"\n📈 Analysis for contract: {token}")
                print(analysis)
                print("\n" + "="*50 + "\n")
            
            # Show recommendations summary (without reasoning)
            cprint("\n📊 Moon Dev's Trading Recommendations:", "white", "on_blue")
            summary_df = self.recommendations_df[['token', 'action', 'confidence']].copy()
            print(summary_df.to_string(index=False))
            
            # First handle any exits based on recommendations
            cprint("\n🔄 Checking for positions to exit...", "white", "on_blue")
            
            # Handle exits first - close any positions where recommendation is SELL or NOTHING
            for _, row in self.recommendations_df.iterrows():
                token = row['token']
                action = row['action']
                
                if action in ["SELL", "NOTHING"]:
                    current_position = n.get_token_balance_usd(token)
                    if current_position > 0:
                        cprint(f"\n🚫 AI Agent recommends {action} for {token}", "white", "on_yellow")
                        cprint(f"💰 Current position: ${current_position:.2f}", "white", "on_blue")
                        try:
                            cprint(f"📉 Closing position with chunk_kill...", "white", "on_cyan")
                            n.chunk_kill(token, max_usd_order_size, slippage)
                            cprint(f"✅ Successfully closed position", "white", "on_green")
                        except Exception as e:
                            cprint(f"❌ Error closing position: {str(e)}", "white", "on_red")
            
            # Then proceed with new allocations for BUY recommendations
            cprint("\n💰 Calculating optimal portfolio allocation...", "white", "on_blue")
            allocation = self.allocate_portfolio()
            
            if allocation:
                cprint("\n💼 Moon Dev's Portfolio Allocation:", "white", "on_blue")
                print(json.dumps(allocation, indent=4))
                
                cprint("\n🎯 Executing allocations...", "white", "on_blue")
                self.execute_allocations(allocation)
                cprint("\n✨ All allocations executed!", "white", "on_blue")
            else:
                cprint("\n⚠️ No allocations to execute!", "white", "on_yellow")
            
            # Clean up temp data
            cprint("\n🧹 Cleaning up temporary data...", "white", "on_blue")
            try:
                for file in os.listdir('temp_data'):
                    if file.endswith('_latest.csv'):
                        os.remove(os.path.join('temp_data', file))
                cprint("✨ Temp data cleaned successfully!", "white", "on_green")
            except Exception as e:
                cprint(f"⚠️ Error cleaning temp data: {str(e)}", "white", "on_yellow")
                
        except Exception as e:
            cprint(f"\n❌ Error in trading cycle: {str(e)}", "white", "on_red")
            cprint("🔧 Moon Dev suggests checking the logs and trying again!", "white", "on_blue")

    def parse_allocation_response(self, response):
        """Parse the AI's allocation response and clean it to valid JSON"""
        try:
            # Find the JSON block between curly braces
            start = response.find('{')
            end = response.rfind('}') + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON object found in response")
            
            json_str = response[start:end]
            
            # Remove comments (anything after #)
            json_lines = []
            for line in json_str.split('\n'):
                comment_pos = line.find('#')
                if comment_pos != -1:
                    line = line[:comment_pos]
                json_lines.append(line)
            
            # Rejoin and ensure it's valid JSON
            cleaned_json = '\n'.join(json_lines)
            
            # Remove trailing commas which are invalid in JSON
            cleaned_json = cleaned_json.replace(',}', '}')
            cleaned_json = cleaned_json.replace(',\n}', '\n}')
            
            # Parse the cleaned JSON
            allocations = json.loads(cleaned_json)
            
            # Validate allocations
            for token, amount in allocations.items():
                if not isinstance(amount, (int, float)):
                    raise ValueError(f"Invalid allocation amount for {token}: {amount}")
                
            return allocations
            
        except Exception as e:
            cprint(f"❌ Error parsing allocation response: {str(e)}", "red")
            cprint("Raw response:", "yellow")
            print(response)
            return None

def main():
    """Main function to run the trading agent every 15 minutes"""
    cprint("🌙 Moon Dev AI Trading System Starting Up! 🚀", "white", "on_blue")
    
    agent = TradingAgent()
    INTERVAL = RUN_INTERVAL_MINUTES * 60  # Convert minutes to seconds
    
    while True:
        try:
            agent.run_trading_cycle()
            
            next_run = datetime.now() + timedelta(minutes=RUN_INTERVAL_MINUTES)
            cprint(f"\n⏳ AI Agent run complete. Next run at {next_run.strftime('%Y-%m-%d %H:%M:%S')}", "white", "on_green")
            
            # Sleep until next interval
            time.sleep(INTERVAL)
                
        except KeyboardInterrupt:
            cprint("\n👋 Moon Dev AI Agent shutting down gracefully...", "white", "on_blue")
            break
        except Exception as e:
            cprint(f"\n❌ Error: {str(e)}", "white", "on_red")
            cprint("🔧 Moon Dev suggests checking the logs and trying again!", "white", "on_blue")
            # Still sleep and continue on error
            time.sleep(INTERVAL)

if __name__ == "__main__":
    main() 