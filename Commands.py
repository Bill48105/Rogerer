# coding=utf8
import sys, os, subprocess, time, datetime, math, pprint, traceback, operator, random
import Irc, Transactions, Blocknotify, Logger, Global, Hooks, Config
from collections import OrderedDict

# nickserv_help_string = "You are not identified with freenode services (see /msg NickServ help - https://freenode.net/kb/answer/registration)"

def validate_user(acct, host = False, nick = False, altnick = False, allow_discord_nicks = False, hostlist = []):
	msg = True
	if not acct:
		msg = "You are not identified with freenode services (see /msg NickServ help - https://freenode.net/kb/answer/registration)"
	elif allow_discord_nicks and host in hostlist and hostlist[host].lower() != acct.lower() and not any(x.lower() == nick.lower() for x in Config.config["bridgebotnicks"]):
		Transactions.lock(acct, True)
		Logger.irclog("Locked %s for using multiple accts (Previous acct: %s, Current acct: %s)" % (nick, hostlist[host], acct))
	if Transactions.lock(acct):
		msg = "Your account is currently locked"
	if msg == True and allow_discord_nicks and any(x.lower() == nick.lower() for x in Config.config["bridgebotnicks"]):
		check_acct_exists = Transactions.check_exists(altnick, check_alt = altnick)
		if check_acct_exists and not Transactions.lock(acct) and not Transactions.lock(altnick):
			acct = check_acct_exists
		else:
			acct = False
			msg = "Quiet"
		return msg, acct
	elif allow_discord_nicks:
		return msg, acct
	return msg

def random_line(file):
	with open(file,'r') as afile:
		line = next(afile)
		for num, aline in enumerate(afile):
			if not bool(aline.strip()) or random.randrange(num + 2): continue
			line = aline
	return line.strip()

def coloured_text(text = "", colour = False, rainbow = False, channel = False):
	if channel and channel in Config.config["stripcolours"]:
		return text
	first = True
	if rainbow:
		text = str(text)
		sep = ""
	else:
		text = text.split()
		sep = " "
	coloured_string = ""
	for t in text:
		if first:
			onesep = ""
		else:
			onesep = sep
		if not colour or rainbow:
			colour = "%02d" % (random.randint(0,15),)
		coloured_string = "%s%s\x03%s%s\x03" % (coloured_string, onesep, colour, t)
		first = False
	return coloured_string

commands = {}

def ping(req, _):
	"""%ping - Pong"""
	req.reply("Pong")
commands["ping"] = ping

def balance(req, _):
	"""%balance - Displays your confirmed and unconfirmed balance"""
	acct = Irc.account_names([req.nick])[0]
	user_valid = validate_user(acct)
	if user_valid != True: return req.notice_private(user_valid)
	confirmed = Transactions.balance(acct)
	pending = Transactions.balance_unconfirmed(acct)
	if pending:
		req.reply("Your balance is %i %s (+%i %s unconfirmed)" % (confirmed, Config.config["coinab"], pending, Config.config["coinab"]))
	else:
		req.reply("Your balance is %i %s" % (confirmed, Config.config["coinab"]))
commands["balance"] = balance
commands["bal"] = balance

def deposit(req, _):
	"""%deposit - Displays your deposit address"""
	acct = Irc.account_names([req.nick])[0]
	user_valid = validate_user(acct)
	if user_valid != True: return req.notice_private(user_valid)
	req.reply("To deposit, send coins to %s (transactions will be credited after %d confirmations)" % (Transactions.deposit_address(acct), Config.config["confirmations"]))
commands["deposit"] = deposit

def parse_amount(s, acct = False, all_offset = 0, min_amount = 1, integer_only = True, roundDown = False):
	if acct and s.lower() == "all":
		return max(Transactions.balance(acct) + all_offset, 1)
	elif s.lower() == "burger":
		return 4
	elif s.lower() == "testicle":
		return 10
	elif s.lower() == "testicles":
		return 20
	elif s.lower() == "penis":
		return 30
	elif s.lower() == "anus":
		return 10
	elif s.lower() == "vagina":
		return 100
	elif s.lower() == "splashback":
		return 500
	elif s.lower() == "goldenshower":
		return 3000
	elif s.lower() == "bugbounty":
		return 8000
	else:
		try:
			amount = float(s)
			if math.isnan(amount):
				raise ValueError
		except ValueError:
			raise ValueError(repr(s) + " - invalid amount")
		if amount > 1e12:
			raise ValueError(repr(s) + " - invalid amount (value too large)")
		if amount < min_amount:
			raise ValueError(repr(s) + " - invalid amount (must be 1 or more)")
		if integer_only and not roundDown and not int(amount) == amount:
			raise ValueError(repr(s) + " - invalid amount (should be integer)")
		if len(str(float(amount)).split(".")[1]) > 8:
			raise ValueError(repr(s) + " - invalid amount (max 8 digits)")
		if integer_only:
			return int(amount)
		else:
			return amount

def is_soak_ignored(account):
	if "soakignore" in Config.config:
		return Config.config["soakignore"].get(account.lower(), False)
	else:
		return False

def withdraw(req, arg):
	"""%withdraw <address> <amount> - Sends 'amount' coins to the specified 'address'. If no 'amount' specified, sends the whole balance"""
	if len(arg) == 0:
		return req.reply(gethelp("withdraw"))
	acct = Irc.account_names([req.nick])[0]
	user_valid = validate_user(acct)
	if user_valid != True: return req.notice_private(user_valid)
	if len(arg) == 1:
		amount = max(Transactions.balance(acct) - Config.config["txfee"], 1)
	else:
		try:
			amount = parse_amount(arg[1], acct, all_offset = -1)
		except ValueError as e:
			return req.notice_private(str(e))
	to = arg[0]
	if not Transactions.verify_address(to):
		return req.notice_private("%s doesn't seem to be a valid %s address" % (to, Config.config["coinab"]))
	token = Logger.token()
	try:
		tx = Transactions.withdraw(token, acct, to, amount)
		req.reply("Coins have been sent, see https://explorer.theholyroger.com/tx/%s [%s]" % (tx, token))
	except Transactions.NotEnoughMoney:
		req.notice_private("You tried to withdraw %i %s (+%.3f %s TX fee) but you only have %i %s" % (amount, Config.config["coinab"], Config.config["txfee"], Config.config["coinab"], Transactions.balance(acct), Config.config["coinab"]))
	except Transactions.InsufficientFunds:
		req.reply("Something went wrong, report this to TheHoliestRoger [%s]" % (token))
		Logger.irclog("InsufficientFunds while executing '%s' from '%s'" % (req.text, req.nick))
	except Exception as e:
		Logger.irclog("Withdraw failed:  '%s'" % (e))
		Logger.log("ce","Withdraw failed: '%s'" % (e))
commands["withdraw"] = withdraw

def target_nick(target):
	return target.split("@", 1)[0]

def target_verify(target, accname):
	s = target.split("@", 1)
	if len(s) == 2:
		return Irc.equal_nicks(s[1], accname)
	else:
		return True

def tip(req, arg, from_instance = False):
	"""%tip <nickname> <amount> - Sends 'amount' coins to the specified 'nickname'. Nickname can be suffixed with @ and an account name, if you want to make sure you are tipping the correct person"""
	if len(arg) < 2:
		return req.reply(gethelp("tip"))
	to = arg[0]
	if req.cmdalias == "slap":
		tip_str = "slapped %s across the face with" % (target_nick(to))
	elif req.cmdalias == "tickle":
		tip_str = "tickled %s with" % (target_nick(to))
	else:
		tip_str = "gifted %s with" % (target_nick(to))
	acct, toacct = Irc.account_names([req.nick, target_nick(to)])
	nick = req.nick
	if from_instance:
		acct = Irc.account_names([req.instance])[0]
		nick = req.instance
	user_valid = validate_user(acct)
	if user_valid != True: return req.notice_private(user_valid)
	if not toacct:
		check_acct_exists = Transactions.check_exists(to)
		if check_acct_exists:
			toacct = check_acct_exists
		elif toacct == None:
			return req.reply("%s is not online" % (target_nick(to)))
		else:
			return req.reply("%s is not identified with freenode services" % (target_nick(to)))
	if not target_verify(to, toacct):
		return req.notice_private("Account name mismatch")
	try:
		if len(arg) > 2:
			amount = 0
			for i in range(1,len(arg)):
				amount = amount + parse_amount(arg[i], acct)
		else:
			amount = parse_amount(arg[1], acct)
	except ValueError as e:
		return req.notice_private(str(e))
	if amount > 99999:
		return req.say("%s tipped %i %s to %s from alohaferret's cold storage!" % (nick, amount, Config.config["coinab"], target_nick(to)))
	token = Logger.token()
	try:
		Transactions.tip(token, acct, toacct, amount)
		if Irc.equal_nicks(req.nick, req.target):
			req.reply("Done [%s]" % (token))
		else:
			req.say("%s %s %i %s!" % (nick, tip_str, amount, Config.config["coinab"]))
			# req.notice_private("Tip ID: [%s]" % (token))
		req.noticemsg(target_nick(to), "%s has tipped you %i %s (to claim /msg %s help) [%s]" % (nick, amount, Config.config["coinab"], req.instance, token), priority = 10)
	except Transactions.NotEnoughMoney:
		req.notice_private("You tried to tip %i %s but you only have %i %s" % (amount, Config.config["coinab"], Transactions.balance(acct), Config.config["coinab"]))
commands["tip"] = tip
commands["slap"] = tip
commands["tickle"] = tip

def mtip(req, arg):
	"""%mtip <targ1> <amt1> [<targ2> <amt2> ...] - Send multiple tips at once"""
	if not len(arg) or len(arg) % 2:
		return req.reply(gethelp("mtip"))
	acct = Irc.account_names([req.nick])[0]
	user_valid = validate_user(acct)
	if user_valid != True: return req.notice_private(user_valid)
	for i in range(0, len(arg), 2):
		try:
			arg[i + 1] = parse_amount(arg[i + 1], acct)
		except ValueError as e:
			return req.notice_private(str(e))
	targets = []
	amounts = []
	total = 0
	for i in range(0, len(arg), 2):
		target = arg[i]
		amount = arg[i + 1]
		found = False
		for i in range(len(targets)):
			if Irc.equal_nicks(targets[i], target):
				amounts[i] += amount
				total += amount
				found = True
				break
		if not found:
			targets.append(target)
			amounts.append(amount)
			total += amount
	balance = Transactions.balance(acct)
	if total > balance:
		return req.notice_private("You tried to tip %i %s but you only have %i %s" % (total, Config.config["coinab"], balance, Config.config["coinab"]))
	accounts = Irc.account_names([target_nick(target) for target in targets])
	totip = {}
	failed = ""
	tipped = ""
	for i in range(len(targets)):
		if accounts[i] == None:
			failed += " %s (offline)" % (target_nick(targets[i]))
		elif accounts[i] == False:
			failed += " %s (unidentified)" % (target_nick(targets[i]))
		elif not target_verify(targets[i], accounts[i]):
			failed += " %s (mismatch)" % (targets[i])
		else:
			totip[accounts[i]] = totip.get(accounts[i], 0) + amounts[i]
			tipped += " %s %d" % (target_nick(targets[i]), amounts[i])
	token = Logger.token()
	try:
		Transactions.tip_multiple(token, acct, totip)
		tipped += " [%s]" % (token)
	except Transactions.NotEnoughMoney:
		return req.notice_private("You tried to tip %i %s but you only have %i %s" % (total, Config.config["coinab"], Transactions.balance(acct), Config.config["coinab"]))
	output = "Tipped:" + tipped
	if len(failed):
		output += "  Failed:" + failed
	req.reply(output)
commands["mtip"] = mtip

def faucet(req, arg):
	"""%faucet - Sends you a random amount of coins from the pot"""
	if len(arg) > 0:
		if arg[0] == "winners" or arg[0] == "top" or arg[0] == "leaders":
			runnerup1_row = Transactions.faucet_board(req.instance,'runnerup1')
			if runnerup1_row:
				runnerup1_time = datetime.datetime.fromtimestamp(int(runnerup1_row[0])).strftime('%Y-%m-%d')
				str_runner1 = (" Last runnerup was %s (%i %s) on %s." % (runnerup1_row[1], runnerup1_row[2], Config.config["coinab"], runnerup1_time))
			else:
				str_runner1 = ""
			jackpot_row = Transactions.faucet_board(req.instance,'jackpot')
			if jackpot_row:
				jackpot_time = datetime.datetime.fromtimestamp(int(jackpot_row[0])).strftime('%Y-%m-%d')
				str_jackpot = (" Last jackpot winner was %s (%i %s) on %s." % (jackpot_row[1], jackpot_row[2], Config.config["coinab"], jackpot_time))
			else:
				str_jackpot = ""
			topwinner_row = Transactions.faucet_board(req.instance,'topwinner')
			if topwinner_row:
				topwinner_time = datetime.datetime.fromtimestamp(int(topwinner_row[0])).strftime('%Y-%m-%d')
				if not runnerup1_row and not jackpot_row:
					str_topwinner_p = "Highest winner so far is"
				else:
					str_topwinner_p = "Followed by"
				str_topwinner = (" %s %s (%i %s) on %s!" % (str_topwinner_p, topwinner_row[1], topwinner_row[2], Config.config["coinab"], topwinner_time))
			else:
				str_topwinner = ""
			return req.say("%s%s%s" % (str_jackpot, str_runner1, str_topwinner))
		if arg[0] == "losers" or arg[0] == "bottom":
			loser_row = Transactions.faucet_board(req.instance,'losers')
			if loser_row:
				loser_time = datetime.datetime.fromtimestamp(int(loser_row[0])).strftime('%Y-%m-%d')
				str_loser_p = "The loser is"
				str_loser = ("%s %s (%i %s) on %s!" % (str_loser_p, loser_row[1], loser_row[2], Config.config["coinab"], loser_time))
			else:
				str_loser = "No loser yet!"
			return req.say("%s" % (str_loser))
	toacct = Irc.account_names([req.nick])[0]
	host = Irc.get_host(req.source)
	curtime = time.time()
	random.seed(curtime*1000)
	user_valid, toacct = validate_user(toacct, host = host, nick = req.nick, altnick = req.altnick, allow_discord_nicks = True, hostlist = Global.faucet_list)
	if user_valid != True:
		if "Quiet" == user_valid: return
		return req.notice_private(user_valid)
	if is_soak_ignored(toacct):
		return
	if req.target == req.nick and not Irc.is_super_admin(req.source):
		return req.reply("Can't faucet in private!")
	timer = random.randint((60*60),(4*60*60))
	if toacct in Global.faucet_list and Global.faucet_list[toacct] + timer > curtime:
		if Global.faucet_list[toacct] + timer > curtime + (5*60) and Global.faucet_list[toacct] + timer < curtime + (40*24*60*60):
			penalty = random.randint((30*60),(2*60*60))
			Global.faucet_list[toacct] = Global.faucet_list[toacct] + penalty
		timerApprx = random.randint(timer,timer+(20*60))
		difference = (Global.faucet_list[toacct] + timerApprx - curtime)/60
		if difference > 60:
			difference = difference/60
			timeUnit = "hours"
		else:
			timeUnit = "minutes"
		return req.reply("Sorry, no %ss around here! Try in %.1f %s." % (Config.config["coinab"], difference, timeUnit), True)
	acct = req.instance
	lotto=[]
	for i in range (946):
		lotto.append(random.randint(1,50)) 	# 94.6% chance of dropping 1-50 ROGER
	for i in range (40):
		lotto.append(random.randint(51,200)) 	# 4% chance of dropping 51-200 ROGER
	for i in range (10):
		lotto.append(random.randint(201,500)) 	# 1% chance of dropping 201-500 ROGER
	for i in range (3):
		lotto.append(random.randint(1000,2000)) # 0.3% chance of dropping 1000-2000 ROGER
	for i in range (1):
		lotto.append(6000) 					# 0.1% chance of dropping 6000 ROGER
	amount = str(random.choice(lotto))
	try:
		amount = parse_amount(amount, acct)
	except ValueError as e:
		return req.notice_private(str(e))
	topwinner_row = Transactions.faucet_board(req.instance,'topwinner')
	loser_row = Transactions.faucet_board(req.instance,'losers')
	if not topwinner_row or (amount >= topwinner_row[2] and amount < 1000):
		newhighest = " (New high!)"
	elif not loser_row or (amount <= loser_row[2] and amount < 1000):
		newhighest = " (New low!)"
	else:
		newhighest = ""
	token = Logger.token()
	try:
		Transactions.tip(token, acct, toacct, amount, tip_source = "@FAUCET")
		quote = str(random_line('quotes_faucet'))
		req.say("%s found %i %s ($0.00)! %s%s (@Pot = %i)" % (req.altnick, amount, Config.config["coinab"], quote, newhighest, Transactions.balance(req.instance)))
		Global.faucet_list[toacct] = curtime
		Global.faucet_list[host] = toacct
		return
	except Transactions.NotEnoughMoney:
		req.reply("We're all out of %s!!" % (Config.config["coinab"]), True)
		return
commands["faucet"] = faucet

def active(req, arg):
	"""%active <minutes> - Lists out number of active users over past x 'minutes' (default 1440)"""
	acct = Irc.account_names([req.nick])[0]
	user_valid = validate_user(acct)
	if user_valid != True: return req.notice_private(user_valid)
	for i in range(0, len(arg), 1):
			try:
					arg[i] = parse_amount(arg[i], acct)
			except ValueError as e:
					return req.notice_private(str(e))
	activeseconds = 86400
	if len(arg) > 0:
			activeseconds = int(arg[0]) * 60
	if activeseconds < 60:
			activeseconds = 600
	elif activeseconds > 86400:
			activeseconds = 86400
	curtime = time.time()
	targets = []
	targetnicks = []
	for oneactive in Global.account_cache[req.target].keys():
			try:
					curactivetime = curtime - Global.active_list[req.target][oneactive]
			except:
					curactivetime = -1 # if not found default to expired
			target = oneactive
			if target != None and target != acct and target != req.nick and target != req.instance and target not in targets and not is_soak_ignored(target) and curactivetime > 0 and curactivetime < activeseconds:
					targets.append(target)
					if Irc.getacctnick(target) and not Global.acctnick_list[target] == None:
							targetnicks.append(str(Global.acctnick_list[target]))
					else:
							targetnicks.append(str(target))
	accounts = Irc.account_names(targetnicks)
	failedcount = 0
	# we need a count of how many will fail to do calculations so pre-loop list
	for i in range(len(accounts)):
			if not accounts[i] or accounts[i] == None:
					failedcount += 1
	output = "I see %d eligible active users in the past %d minutes." % (len(targets) - failedcount,int(activeseconds/60))
	req.reply(output)
commands["active"] = active

def soak(req, arg, from_instance = False):
	"""%soak <amt> <minutes> - Sends each active user an equal share of soaked 'amount'"""
	if not len(arg) or len(arg) % 1:
			return req.reply(gethelp("soak"))
	acct = Irc.account_names([req.nick])[0]
	nick = req.nick
	if from_instance:
		acct = Irc.account_names([req.instance])[0]
		nick = req.instance
	user_valid = validate_user(acct)
	if user_valid != True: return req.notice_private(user_valid)
	for i in range(0, len(arg), 1):
			try:
					arg[i] = parse_amount(arg[i], acct)
			except ValueError as e:
					return req.notice_private(str(e))
	activeseconds = 86400
	if len(arg) > 1:
			activeseconds = int(arg[1]) * 60
	if activeseconds < 60:
			activeseconds = 600
	elif activeseconds > 86400:
			activeseconds = 86400
	curtime = time.time()
	targets = []
	targetnicks = []
	failed = ""
	if req.target == req.nick:
		return req.reply("Can't soak in private!")
	for oneactive in Global.account_cache[req.target].keys():
			try:
					curactivetime = curtime - Global.active_list[req.target][oneactive]
			except:
					curactivetime = -1 # if not found default to expired
			target = oneactive
			if target != None and target != acct and target != nick and target != req.instance and target not in targets and not is_soak_ignored(target) and curactivetime > 0 and curactivetime < activeseconds:
					targets.append(target)
					if Irc.getacctnick(target) and not Global.acctnick_list[target] == None:
							targetnicks.append(str(Global.acctnick_list[target]))
					else:
							targetnicks.append(str(target))

	accounts = Irc.account_names(targetnicks)
	failedcount = 0
	# we need a count of how many will fail to do calculations so pre-loop list
	for i in range(len(accounts)):
			if not accounts[i] or accounts[i] == None:
					Global.account_cache.setdefault(req.target, {})[targetnicks[i]] = None
					failedcount += 1
	MinActive = 1
	if (len(targets) - failedcount) < MinActive:
			return req.reply("This place seems dead. (Maybe try specifying more minutes..)")
	scraps = 0
	amount = int(arg[0] / (len(targets) - failedcount))
	total = (len(targets) - failedcount) * amount
	scraps = int(arg[0]) - total
	if scraps <= 0:
			scraps = 0
	balance = Transactions.balance(acct)
	if total <= 0:
			return req.reply("Unable to soak (Not enough to go around, %d %s Minimum)" % ((len(targets) - failedcount), Config.config["coinab"]))
	if total + scraps > balance:
			return req.notice_private("You tried to soak %.0f %s but you only have %.0f %s" % (total+scraps, Config.config["coinab"], balance, Config.config["coinab"]))
	totip = {}
	tipped = ""
	for i in range(len(accounts)):
			if accounts[i]:
					totip[accounts[i]] = amount
					tipped += " %s" % (targetnicks[i])
			elif accounts[i] == None:
					failed += " %s (o)" % (targetnicks[i])
			else:
					failed += " %s (u)" % (targetnicks[i])
	tippednicks = tipped.strip().split(" ")
	# special case where bot isn't included in soak but there are scraps
	if req.instance not in accounts and scraps > 0:
			totip[req.instance] = scraps
			tipped += " %s (%d scraps)" % (req.instance, scraps)
	token = Logger.token()
	try:
			Transactions.tip_multiple(token, acct, totip, tip_source = "@SOAK")
	except Transactions.NotEnoughMoney:
			return req.notice_private("You tried to soak %.0f %s but you only have %.0f %s" % (total, Config.config["coinab"], Transactions.balance(acct), Config.config["coinab"]))
	output = "%s is soaking %d users with %d %s:" % (nick, len(tippednicks), amount, Config.config["coinab"])
	# only show nicks if not too many active, if large enough total (default 1 to always show or change), if nick list changed or if enough time has passed
	if len(tippednicks) > 100 or total + scraps < 1 or ((acct in Global.nicks_last_shown and Global.nicks_last_shown[acct] == tipped) and (acct+":last" in Global.nicks_last_shown and curtime < Global.nicks_last_shown[acct+":last"] + 600)):
			output += " (See previous nick list ) [%s]" % (token)
	else:
			for onetipped in tippednicks:
					if onetipped:
							if len(output) < 250:
									output += " " + onetipped
							else:
									req.reply(output)
									output = " " + onetipped
			Global.nicks_last_shown[acct] = tipped
			Global.nicks_last_shown[acct+":last"] = curtime
	req.say(output)
	Logger.log("c","SOAK %s %s skipped: %s" % (token, repr(targetnicks), repr(failed)))
commands["soak"] = soak

def soakignore(req, arg):
	"""%soakignore <acct> [add/del] - Ignore ACCOUNT (not nick) from soak/rain/etc. Requires manual admin save to be perm"""
	if not len(arg) or len(arg) % 1:
		return req.reply(gethelp("soakignore"))
	acct = Irc.account_names([req.nick])[0]
	user_valid = validate_user(acct)
	if user_valid != True: return req.notice_private(user_valid)
	if not Irc.is_admin(req.source):
		return req.notice_private("You are not authorized to use this command")
	if not "soakignore" in Config.config:
		Config.config['soakignore'] = {}
	if len(arg) > 1 and arg[1] == "del":
		Config.config["soakignore"].pop(arg[0].lower(), False)
	elif len(arg) > 1 and arg[1] == "add":
		Config.config['soakignore'].update({arg[0].lower():True})
	if not is_soak_ignored(arg[0]):
		output = arg[0] + " is NOT ignored."
	else:
		output = arg[0] + " is ignored."
	req.reply(output)
commands["soakignore"] = soakignore

def donate(req, arg):
	"""%donate <amount> - Donate 'amount' coins to help fund the faucet"""
	if len(arg) < 1:
		return req.reply(gethelp("donate"))
	acct = Irc.account_names([req.nick])[0]
	user_valid = validate_user(acct)
	if user_valid != True: return req.notice_private(user_valid)
	toacct = req.instance
	try:
		amount = parse_amount(arg[0], acct)
	except ValueError as e:
		return req.notice_private(str(e))
	token = Logger.token()
	try:
		Transactions.tip(token, acct, toacct, amount)
		req.reply("Donated %i %s, thank you very much for your donation [%s]" % (amount, Config.config["coinab"], token))
	except Transactions.NotEnoughMoney:
		req.notice_private("You tried to donate %i %s but you only have %i %s" % (amount, Config.config["coinab"], Transactions.balance(acct), Config.config["coinab"]))
commands["donate"] = donate

def gethelp(name):
	if name[0] == Config.config["prefix"]:
		name = name[1:]
	cmd = commands.get(name, None)
	if cmd and cmd.__doc__:
		return cmd.__doc__.split("\n")[0].replace("%", Config.config["prefix"])

def _help(req, arg):
	"""%help - list of commands; %help <command> - help for specific command"""
	if len(arg):
		h = gethelp(arg[0])
		if h:
			req.reply(h)
	else:
		if not Irc.equal_nicks(req.target, req.nick):
			req.reply("I'm %s, a %s tipbot. For more info check your PMs" % (req.instance, Config.config["coinab"]))
		acct = Irc.account_names([req.nick])[0]
		if acct:
			ident = "you're identified as \2" + acct + "\2"
		else:
			ident = "you're \2NOT\2 identified!! :O \2SEE %sREGISTER\2" % (Config.config["prefix"])
		# List of commands to not show users in help
		hidecmd = ["as", "admin"]
		allcmd = ""
		sortedcmd = OrderedDict(sorted(commands.items(), key=operator.itemgetter(0)))
		for onecmd in sortedcmd:
			if not onecmd in hidecmd:
				allcmd += Config.config["prefix"][0] + onecmd + " "
		req.reply_private("I'm %s, I'm a %s tipbot. To get help about a command, say: \2%shelp <command>\2" % (req.instance, Config.config["coinab"], Config.config["prefix"]))
		req.reply_private("Commands: \2%s\2" % (allcmd))
		req.reply_private("For any support questions, including those related to lost coins, ask \2Roger Ver\2")
		req.reply_private("Note that to receive or send %s you MUST be identified with freenode services (%s)." % (Config.config["coinab"], ident))
commands["help"] = _help

def admin(req, arg):
	"""
	admin"""
	if len(arg) and Irc.is_admin(req.source) or Irc.is_super_admin(req.source):
		command = arg[0]
		arg = arg[1:]
		if command == "reload" and Irc.is_super_admin(req.source):
			for mod in arg:
				reload(sys.modules[mod])
			req.reply("Reloaded")
		elif command == "exec" and Config.config.get("enable_exec", None) and Irc.is_super_admin(req.source):
			try:
				exec(" ".join(arg).replace("$", "\n"))
			except Exception as e:
				type, value, tb = sys.exc_info()
				Logger.log("ce", "ERROR in " + req.instance + " : " + req.text)
				Logger.log("ce", repr(e))
				Logger.log("ce", "".join(traceback.format_tb(tb)))
				req.reply(repr(e))
				req.reply("".join(traceback.format_tb(tb)).replace("\n", " || "))
				del tb
		elif command == "ignore":
			Irc.ignore(arg[0], int(arg[1]))
			req.reply("Ignored")
		elif command == "die" and Irc.is_super_admin(req.source):
			for instance in Global.instances:
				Global.manager_queue.put(("Disconnect", instance))
			Global.manager_queue.join()
			Blocknotify.stop()
			Global.manager_queue.put(("Die",))
		elif command == "restart" and Irc.is_super_admin(req.source):
			for instance in Global.instances:
				Global.manager_queue.put(("Disconnect", instance))
			Global.manager_queue.join()
			Blocknotify.stop()
			os.execv(sys.executable, [sys.executable] + sys.argv)
		elif command == "manager" and Irc.is_super_admin(req.source):
			for cmd in arg:
				Global.manager_queue.put(cmd.split("$"))
			req.reply("Sent")
		elif command == "raw" and Irc.is_super_admin(req.source):
			Irc.instance_send(req.instance, eval(" ".join(arg)))
		elif command == "config" and Irc.is_super_admin(req.source):
			if arg[0] == "save":
				os.rename("Config.py", "Config.py.bak")
				with open("Config.py", "w") as f:
					f.write("config = " + pprint.pformat(Config.config) + "\n")
				req.reply("Done")
			elif arg[0] == "del":
				exec("del Config.config " + " ".join(arg[1:]))
				req.reply("Done")
			else:
				try:
					req.reply(repr(eval("Config.config " + " ".join(arg))))
				except SyntaxError:
					exec("Config.config " + " ".join(arg))
					req.reply("Done")
		elif command == "join" and Irc.is_super_admin(req.source):
			Irc.instance_send(req.instance, ("JOIN", arg[0]), priority = 0.1)
		elif command == "part" and Irc.is_super_admin(req.source):
			Irc.instance_send(req.instance, ("PART", arg[0]), priority = 0.1)
		elif command == "caches" and Irc.is_super_admin(req.source):
			acsize = 0
			accached = 0
			with Global.account_lock:
				for channel in Global.account_cache:
					for user in Global.account_cache[channel]:
						acsize += 1
						if Global.account_cache[channel][user] != None:
							accached += 1
			acchannels = len(Global.account_cache)
			whois = " OK"
			whoisok = True
			for instance in Global.instances:
				tasks = Global.instances[instance].whois_queue.unfinished_tasks
				if tasks:
					if whoisok:
						whois = ""
						whoisok = False
					whois += " %s:%d!" % (instance, tasks)
			req.reply("Account caches: %d user-channels (%d cached) in %d channels; Whois queues:%s" % (acsize, accached, acchannels, whois))
		elif command == "channels":
			inss = ""
			for instance in Global.instances:
				chans = []
				with Global.account_lock:
					for channel in Global.account_cache:
						if instance in Global.account_cache[channel]:
							chans.append(channel)
				inss += " %s:%s" % (instance, ",".join(chans))
			req.reply("Instances:" + inss)
		elif command == "balances":
			database, theholyrogerd = Transactions.balances()
			botconfirmed = Transactions.balance(req.instance)
			botpending = Transactions.balance_unconfirmed(req.instance)
			req.reply("Node Wallet: %.2f; Database: %.2f; Bot Account: %.2f (%.2f unconfirmed)" % (theholyrogerd, database, botconfirmed, botpending))
		elif command == "balance":
			if len(arg):
				target = arg[0]
				targetacct = Irc.account_names([target_nick(target)])[0]
				if not targetacct:
					targetacct = target
				if targetacct:
					targetbal = Transactions.balance(targetacct)
					req.reply("%s's balance is %i %s" % (target, targetbal, Config.config["coinab"]))
				else:
					req.reply("%s not found in database." % (target))
		elif command == "blocks":
			mining_info, net_info, hashd = Transactions.get_all_info()
			hashb = Transactions.lastblock.encode("ascii")
			req.reply("Best block: %s, Last tx block: %s, Blocks: %s" % (hashd, hashb, mining_info.blocks))
		elif command == "info":
			mining_info, net_info, hashd = Transactions.get_all_info()
			req.reply("TheHolyRogerCoin (ROGER) v3r | Client: %s | Proto: %s | Blocks: %s | Diff: %.2f | Network Hash: %.3f GH | Conns: %s " % (net_info.version, net_info.protocolversion, mining_info.blocks, mining_info.difficulty, (mining_info.networkhashps/1000000000), net_info.connections))
		elif command == "lock":
			if len(arg) > 1:
				if arg[1] == "on":
					Transactions.lock(arg[0], True)
				elif arg[1] == "off" and Irc.is_super_admin(req.source):
					Transactions.lock(arg[0], False)
				req.reply("Done")
			elif len(arg):
				req.reply("locked" if Transactions.lock(arg[0]) else "not locked")
		elif command == "update" and Irc.is_super_admin(req.source):
			output = subprocess.check_output(["git", "pull"])
			req.reply("%s" % (output) if output else "Failed")
		elif command == "merge-reset" and Irc.is_super_admin(req.source) and len(arg) == 1:
			output = subprocess.check_output(["git", "fetch"])
			req.reply("%s" % (output) if output else "Failed")
			output = subprocess.check_output(["git", "reset", "--hard", arg[0]])
			req.reply("%s" % (output) if output else "Failed")
		elif command == "host":
			if len(arg) > 1 and arg[0] in Global.faucet_list:
				Global.faucet_list[arg[0]] = arg[1]
				req.reply("Done")
			elif len(arg) and arg[0] in Global.faucet_list:
				req.reply("Host [%s] assigned to [%s]" % (arg[0], Global.faucet_list[arg[0]]) if arg[0] in Global.faucet_list else "Host [%s] does not exist" % (arg[0]))
		elif command == "faucetreset":
			if len(arg) > 1 and arg[0] in Global.faucet_list:
				Global.faucet_list.pop(arg[0])
				req.reply("Done")
			elif len(arg) and arg[0] in Global.faucet_list:
				req.reply("Faucet [%s] timer at [%s]" % (arg[0], datetime.datetime.fromtimestamp(int(Global.faucet_list[arg[0]])).strftime('%Y-%m-%d %H:%M')) if arg[0] in Global.faucet_list else "User [%s] does not exist" % (arg[0]))
		elif command == "gamblereset":
			if len(arg) == 2 and arg[0] in Global.gamble_list and (arg[1] == "now" or arg[1] == "del"):
				Global.gamble_list.pop(arg[0])
				req.reply("Done")
			elif len(arg) == 3 and arg[0] in Global.gamble_list and arg[1] in Global.gamble_list[(arg[0])] and (arg[2] == "now" or arg[2] == "del"):
				Global.gamble_list[(arg[0])].pop(arg[1])
				req.reply("Done")
			elif len(arg) == 2 and arg[0] in Global.gamble_list:
				req.reply("Gamble [%s] timer at [%s]" % (arg[1], datetime.datetime.fromtimestamp(int(Global.gamble_list[(arg[0])][(arg[1])])).strftime('%Y-%m-%d %H:%M')) if arg[1] in Global.gamble_list[(arg[0])] else "User [%s] does not exist" % (arg[1]))
			elif len(arg) == 1 and arg[0] in Global.gamble_list:
				req.reply("Gamble timers: [%s]" % (Global.gamble_list[(arg[0])]))
			elif len(arg) < 1:
				req.reply("Gamble timers: [%s]" % (Global.gamble_list))
		elif command == "gamblelock":
			if len(arg) == 3 and arg[2].isdigit():
				Global.gamble_list[(arg[0])][(arg[1])] = time.time() + (60*60*int(arg[2]))
				req.reply("Locked %s for %s hours" % (arg[1],arg[2]))
		elif command == "temp-gamble-limit":
			t = time.time()
			if "@gamblelimitraise" not in Global.gamble_list:
				Global.gamble_list["@gamblelimitraise"] = {}
			if "@gamblelimitraise" in Global.gamble_list:
				if len(arg) == 2 and arg[0] in Global.gamble_list["@gamblelimitraise"] and arg[1] == "del":
					Global.gamble_list["@gamblelimitraise"].pop(arg[0])
					req.reply("Done")
				elif len(arg) == 2:
					try:
						maxbet = parse_amount(arg[1])
					except ValueError as e:
						return req.notice_private(str(e))
					# Global.gamble_list["@gamblelimitraise"][arg[0]] = arg[1]
					Global.gamble_list["@gamblelimitraise"][arg[0]] = {}
					Global.gamble_list["@gamblelimitraise"][arg[0]]["limit"] = maxbet
					Global.gamble_list["@gamblelimitraise"][arg[0]]["time"] = t
					req.reply("Done")
				elif len(arg) == 1 and arg[0] == "clearall":
					Global.gamble_list["@gamblelimitraise"] = {}
					req.reply("Done")
				elif len(arg) == 1 and arg[0] == "show":
					req.reply("Gamble limits: %s" % (Global.gamble_list["@gamblelimitraise"]))
		elif command == "readreset":
			if len(arg) > 1 and arg[0] in Global.response_read_timers:
				Global.response_read_timers.pop(arg[0])
				req.reply("Done")
			elif len(arg) and arg[0] in Global.response_read_timers:
				req.reply("Read Timer: %s" % (Global.response_read_timers[arg[0]]))
			else:
				req.reply("Read Timers: %s" % (Global.response_read_timers))
		elif command == "acc_cache":
			if len(arg) and arg[0] in Global.account_cache:
				req.reply("Account Cache (%s): %s" % (arg[0],Global.account_cache[arg[0]]))
			else:
				req.reply("Account Cache: %s" % (Global.account_cache))
		elif command == "active_list":
			if len(arg) and arg[0] in Global.active_list:
				req.reply("Account Cache (%s): %s" % (arg[0],Global.active_list[arg[0]]))
			else:
				req.reply("Account Cache: %s" % (Global.active_list))
		elif command == "svsdata":
			req.reply("svsdata: %s" % (Global.svsdata))
		elif command == "confetti" or command == "rainbow" or command == "rainbow2":
			reply = ""
			text = ""
			as_rainbow = False
			for x in range(len(arg)):
				if x == 12: break
				word = arg[x][0:20]
				text = "%s %s" % (text, word)
			if command == "rainbow2" and len(text) > 10:
				loops = 3
			else:
				loops = 6
			for i in range(loops):
				bits = [ "' ", ", ", "~ ", ". ", "* ", "^ " ]
				bitstring = ""
				for n in range(7):
					random.shuffle(bits)
					thebit = bits[0]
					bitstring = "%s%s" % (bitstring, coloured_text(text = thebit, channel = req.target))
				if i == 5 or i == 6 or command == "rainbow" or command == "rainbow2":
					bitstring = ""
				if command == "rainbow2":
					as_rainbow = True
				reply = "%s%s %s" % (reply, coloured_text(text = text[0:20], rainbow = as_rainbow, channel = req.target), bitstring)
			req.say(reply)
		elif command == "empty_logfile" and Irc.is_super_admin(req.source):
			Logger.clearlog()
			req.reply("Log Emptied.")
		elif command == "tipfrombot" and Irc.is_super_admin(req.source):
			if len(arg) > 1:
				tip(req, [arg[0], arg[1]], from_instance = True)
				req.reply("Done")
		elif command == "ping":
			t = time.time()
			Irc.account_names(["."])
			pingtime = time.time() - t
			acc = Irc.account_names([req.nick])[0]
			t = time.time()
			Transactions.balance(acc)
			dbreadtime = time.time() - t
			t = time.time()
			Transactions.lock(acc, False)
			dbwritetime = time.time() - t
			t = time.time()
			Transactions.ping()
			rpctime = time.time() - t
			req.reply("Ping: %f, DB read: %f, DB write: %f, RPC: %f" % (pingtime, dbreadtime, dbwritetime, rpctime))
		elif command == "update-mods" and Irc.is_super_admin(req.source):
			if len(arg) > 1:
				if not "admins" in Config.config:
					Config.config['admins'] = {}
				if len(arg) > 1 and arg[1] == "del":
					Config.config["admins"].pop(arg[0].lower(), False)
				elif len(arg) > 1 and arg[1] == "add":
					Config.config['admins'].update({arg[0].lower():True})
				if not Irc.is_admin("dummy@%s" % (arg[0])):
					output = "%s is NOT admin." % (arg[0])
				else:
					output = "%s is admin." % (arg[0])
				req.reply(output)
		elif command == "list-mods-iamsure" and Irc.is_super_admin(req.source):
			if "admins" in Config.config:
				req.reply("Mods: %s" % (Config.config["admins"]))
		elif command == "game-stats" and Irc.is_super_admin(req.source):
			"""game-stats GAME NICK X [DAYS/HOURS/MINUTES]"""
			if len(arg) < 2: return
			game_ident = arg[0]
			nick = arg[1]
			time_amt = 1
			if len(arg) >= 3:
				time_amt = int(arg[2])
			interval = "minutes"
			if len(arg) >= 4:
				if arg[3].lower() == "minutes":
					interval = "minutes"
				elif arg[3].lower() == "hours":
					interval = "hours"
				elif arg[3].lower() == "days":
					interval = "days"
			interval = "%i %s" % (time_amt, interval)
			acct = Irc.account_names([nick])[0]
			InSum = Transactions.get_game_stats(req.instance, mode = "in-sum", game_ident = game_ident, acct = acct, interval = interval, count = False)
			OutSum = Transactions.get_game_stats(req.instance, mode = "out-sum", game_ident = game_ident, acct = acct, interval = interval, count = False)
			InCount = Transactions.get_game_stats(req.instance, mode = "in", game_ident = game_ident, acct = acct, interval = interval, count = True)
			OutCount = Transactions.get_game_stats(req.instance, mode = "out", game_ident = game_ident, acct = acct, interval = interval, count = True)
			Difference = (int(OutSum) - int(InSum))
			req.reply("%s: %s won a total of %i ( %i - %i ), played a total of %i times." % (game_ident, nick, Difference, OutSum, InSum, InCount))
		else:
			req.reply("You are not authorised to use that command.")

commands["admin"] = admin

def price(req, arg):
	"""%price - Checks current price of ROGER."""
	return req.say("Current price of %s: $0.00, stablecoin (1 %s is worth 1 bcash)" % (Config.config["coinab"], Config.config["coinab"]))
commands["price"] = price
commands["value"] = price
commands["val"] = price

def register(req, arg):
	"""%register - How to register with freenode."""
	return req.reply("/msg NickServ help - https://freenode.net/kb/answer/registration")
commands["register"] = register

def info(req, arg):
	"""%info - ROGER network info."""
	mining_info, net_info, hashd = Transactions.get_all_info()
	return req.reply("TheHolyRogerCoin (ROGER) v3r | Client: %s | Protocol: %s | Blocks: %s | Diff: %.2f | Net Hash: %.3f GH | Net Connections: %s " % (net_info.version, net_info.protocolversion, mining_info.blocks, mining_info.difficulty, (mining_info.networkhashps/1000000000), net_info.connections))
commands["info"] = info

def rogerme(req, arg):
	"""%rogerme [ info / address / xchange / mining / explorer / github / irc / quote ] - https://theholyroger.com/The_Holy_Roger_Coin"""
	if len(arg) == 0:
		return req.reply(gethelp("rogerme"))
	if len(arg) == 1:
		command = arg[0]
		if command == "info" or command == "help":
			return req.say("The Holy Roger Coin (ROGER) is developed with a focus on outing scams and trolling The Fake Roger. More info: https://theholyroger.com/The_Holy_Roger_Coin")
		elif command == "address" or command == "paper":
			return req.say("ROGER Paper Wallet: https://address.theholyroger.com")
		elif command == "mining" or command == "pool":
			return req.say("ROGER Mining Pool: https://mining.theholyroger.com")
		elif command == "explorer" or command == "blockchain":
			return req.say("ROGER Explorer: https://explorer.theholyroger.com")
		elif command == "xchange" or command == "exchange":
			return req.say("ROGER Xchange: https://rogerxchange.com")
		elif command == "node" or command == "github" or command == "wallet":
			return req.say("ROGER node & wallet: https://github.com/TheHolyRoger/TheHolyRogerCoin")
		elif command == "irc" or command == "chat" or command == "IRC":
			return req.say("ROGER IRC channel: #TheHolyRoger")
		elif command == "quote" or command == "ver":
			quote = str(random_line('quotes_roger'))
			return req.say("Roger says %s" % (quote))
		elif command == "chuck" or command == "chuckme" or command == "norris" or command == "noris":
			quote = str(random_line('quotes_chuck'))
			return req.say("%s" % (quote))
		elif command == "videos" or command == "video" or command == "clip":
			video = str(random_line('videos_roger'))
			return req.say("Here's your video clip: %s - Enjoy!" % (video))
commands["rogerme"] = rogerme
commands["roger"] = rogerme



def _as(req, arg):
	"""
	admin"""
	_, target, text = req.text.split(" ", 2)
	if target[0] == '@':
		Global.account_cache[""] = {"@": target[1:]}
		target = "@"
	if text.find(" ") == -1:
		command = text
		args = []
	else:
		command, args = text.split(" ", 1)
		args = [a for a in args.split(" ") if len(a) > 0]
	if command[0] != '_':
		cmd = commands.get(command.lower(), None)
		if not cmd.__doc__ or cmd.__doc__.find("admin") == -1 or Irc.is_admin(source) or Irc.is_super_admin(req.source):
			if cmd:
				req = Hooks.FakeRequest(req, target, text)
				Hooks.run_command(cmd, req, args)
	if Global.account_cache.get("", None):
		del Global.account_cache[""]
commands["as"] = _as
