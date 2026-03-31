"""
LLM Decision Agent ⭐
- Central intelligence layer between TA signals and execution
- Configurable backend (Azure OpenAI or AWS Bedrock)
- Final GO / NO-GO decision on every trade
"""

import logging
import json
import os
import time
from typing import Optional, Dict, List, Any
from datetime import datetime
from config import aggressive_config as cfg

logger = logging.getLogger(__name__)

class LLMDecisionAgent:
    """Make final trading decisions using LLM reasoning."""
    
    def __init__(self, state: Dict):
        self.state = state
        self.llm_provider = os.environ.get("LLM_PROVIDER", cfg.LLM_PROVIDER)
        self.timeout_sec = cfg.LLM_TIMEOUT_SECONDS
        self.fallback_on_timeout = cfg.LLM_FALLBACK_ON_TIMEOUT
        
        self._init_llm_client()
    
    def _init_llm_client(self):
        """Initialize LLM client based on provider."""
        if self.llm_provider == "azure":
            try:
                from openai import AzureOpenAI
                self.client = AzureOpenAI(
                    azure_endpoint=cfg.AZURE_OPENAI_ENDPOINT,
                    api_key=os.environ.get("AZURE_OPENAI_KEY", cfg.AZURE_OPENAI_KEY),
                    api_version=cfg.AZURE_API_VERSION,
                )
                logger.info("Azure OpenAI client initialized")
            except Exception as e:
                logger.error(f"Failed to init Azure client: {e}")
                self.client = None
        
        elif self.llm_provider == "bedrock":
            try:
                import boto3
                self.client = boto3.client("bedrock-runtime", region_name=cfg.BEDROCK_REGION)
                logger.info("AWS Bedrock client initialized")
            except Exception as e:
                logger.error(f"Failed to init Bedrock client: {e}")
                self.client = None
        
        else:
            logger.error(f"Unknown LLM provider: {self.llm_provider}")
            self.client = None
    
    def process_signal(self, signal: Dict, account_state: Dict, recent_trades: List[Dict]) -> Optional[Dict]:
        """
        Process a signal through LLM.
        Returns: decision dict with EXECUTE/SKIP/WAIT, adjustments, reasoning
        """
        if not self.client:
            logger.warning("LLM client not available, skipping signal")
            return None
        
        if "llm_pending" not in self.state:
            return None
        
        try:
            # Build context prompt
            prompt = self._build_prompt(signal, account_state, recent_trades)
            
            # Call LLM with timeout
            start_time = time.time()
            response = self._call_llm(prompt)
            elapsed = time.time() - start_time
            
            if response is None:
                logger.warning(f"LLM timeout ({elapsed:.2f}s), applying fallback policy")
                return self._apply_timeout_fallback(signal)
            
            # Parse response
            decision = self._parse_llm_response(response)
            if not decision:
                logger.error("Failed to parse LLM response")
                return None
            
            # Log decision
            self._log_decision(signal, decision, elapsed)
            
            # Apply decision
            return decision
        
        except Exception as e:
            logger.error(f"LLM processing error: {e}")
            return None
    
    def _build_prompt(self, signal: Dict, account_state: Dict, recent_trades: List[Dict]) -> str:
        """Build structured prompt for LLM."""
        current_phase = self.state.get("current_phase", "aggressive")
        days_remaining = self.state.get("days_remaining", 7)
        return_pct = account_state.get("return_pct", 0.0)
        equity = account_state.get("equity", 0.0)
        open_count = len(self.state.get("open_trades", []))
        
        # Format recent trades
        trades_summary = "\n".join([
            f"  {i+1}. {t.get('pair')} {t.get('direction')}: "
            f"{'+' if t.get('pnl', 0) > 0 else ''}{t.get('pnl', 0):.2f} ({t.get('r_multiple', 0):.2f}R)"
            for i, t in enumerate(recent_trades[-5:])
        ]) or "  (none)"
        
        prompt = f"""You are an expert forex trader competing in a 7-day broker competition.
Your goal: maximize equity by end of week.

CURRENT STATE:
- Phase: {current_phase.upper()}
- Return: {return_pct:+.2f}%
- Days remaining: {days_remaining}
- Current equity: ${equity:,.2f}
- Open positions: {open_count}

PROPOSED SIGNAL:
- Pair: {signal['pair']}
- Direction: {signal['direction']}
- Session: {signal['session']}
- Confidence: {signal['confidence']:.2f}
- ATR: {signal['atr']:.5f}
- Indicators fired: {', '.join(signal.get('indicators', []))}
- Risk/Reward: {signal['r_multiple']:.2f}R

RECENT TRADES (last 5):
{trades_summary}

Your task: Decide whether to EXECUTE, SKIP, or WAIT on this signal.
Consider: signal quality, current risk exposure, phase objectives, account state.

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "decision": "EXECUTE|SKIP|WAIT",
  "confidence_adjustment": -0.15,
  "risk_modifier": 0.8,
  "reasoning": "Brief explanation of decision"
}}

Where:
- decision: EXECUTE (place trade), SKIP (discard signal), WAIT (hold 15s)
- confidence_adjustment: -0.30 to +0.20 (relative adjustment)
- risk_modifier: 0.5 to 1.5 (multiplier on standard lot size)
- reasoning: 1-2 sentences explaining the decision"""
        
        return prompt
    
    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call LLM with timeout."""
        try:
            if self.llm_provider == "azure":
                return self._call_azure(prompt)
            elif self.llm_provider == "bedrock":
                return self._call_bedrock(prompt)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None
    
    def _call_azure(self, prompt: str) -> Optional[str]:
        """Call Azure OpenAI."""
        try:
            response = self.client.chat.completions.create(
                model=cfg.AZURE_DEPLOYMENT_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=256,
                timeout=self.timeout_sec,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Azure API error: {e}")
            return None
    
    def _call_bedrock(self, prompt: str) -> Optional[str]:
        """Call AWS Bedrock."""
        try:
            import json
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 256,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            })
            
            response = self.client.invoke_model(
                modelId=cfg.BEDROCK_MODEL_ID,
                body=body,
            )
            
            response_body = json.loads(response["body"].read())
            return response_body["content"][0]["text"]
        except Exception as e:
            logger.error(f"Bedrock API error: {e}")
            return None
    
    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON response from LLM."""
        try:
            # Extract JSON from response (may contain markdown)
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()
            
            data = json.loads(json_str)
            
            # Validate required fields
            if "decision" not in data or data["decision"] not in ["EXECUTE", "SKIP", "WAIT"]:
                logger.warning(f"Invalid decision: {data.get('decision')}")
                return None
            
            # Clamp risk modifier to 0.5-1.5 range
            risk_mod = float(data.get("risk_modifier", 1.0))
            risk_mod = max(0.5, min(1.5, risk_mod))
            
            return {
                "decision": data["decision"],
                "confidence_adjustment": float(data.get("confidence_adjustment", 0.0)),
                "risk_modifier": risk_mod,
                "reasoning": str(data.get("reasoning", "")),
            }
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Response was: {response[:200]}")
            return None
    
    def _apply_timeout_fallback(self, signal: Dict) -> Optional[Dict]:
        """Apply fallback policy when LLM times out."""
        if self.fallback_on_timeout:
            # Execute based on TA alone
            logger.info("LLM timeout fallback: executing TA signal")
            return {
                "decision": "EXECUTE",
                "confidence_adjustment": 0.0,
                "risk_modifier": 0.9,  # Slightly reduce size on LLM timeout
                "reasoning": "LLM timeout, executing TA signal with reduced lot",
            }
        else:
            # Skip trade
            logger.info("LLM timeout fallback: skipping signal")
            return {
                "decision": "SKIP",
                "confidence_adjustment": 0.0,
                "risk_modifier": 1.0,
                "reasoning": "LLM timeout, skipping signal",
            }
    
    def _log_decision(self, signal: Dict, decision: Dict, elapsed: float):
        """Log LLM decision for analysis."""
        os.makedirs(cfg.LOG_DIR, exist_ok=True)
        
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "pair": signal["pair"],
            "direction": signal["direction"],
            "confidence": signal["confidence"],
            "decision": decision["decision"],
            "adjustment": decision["confidence_adjustment"],
            "risk_mod": decision["risk_modifier"],
            "reasoning": decision["reasoning"],
            "elapsed_sec": elapsed,
        }
        
        try:
            with open(cfg.LLM_DECISIONS_LOG, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to log decision: {e}")
