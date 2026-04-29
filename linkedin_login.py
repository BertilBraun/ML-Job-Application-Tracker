from scrapers.browser import get_context

pw, ctx = get_context()
page = ctx.new_page()
page.goto('https://www.linkedin.com/login')
input('Log in, then press Enter...')
ctx.close()
pw.stop()
